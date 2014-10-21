"""Fill device array with a constant value"""

import numpy as np
from . import accel
from . import tune

class FillTemplate(object):
    """
    Fills a device array with a constant value. The pad elements are also
    filled with this value.

    Parameters
    ----------
    context : :class:`cuda.Context` or :class:`opencl.Context`
        Context for which kernels will be compiled
    dtype : numpy dtype
        Type of data elements
    ctype : str
        Type (in C/CUDA, not numpy) of data elements
    tune : dict, optional
        Kernel tuning parameters; if omitted, will autotune. The possible
        parameters are

        - wgs: number of workitems per workgroup
    """

    def __init__(self, context, dtype, ctype, tune=None):
        self.context = context
        self.dtype = np.dtype(dtype)
        self.ctype = ctype
        if tune is None:
            tune = self.autotune(context, dtype, ctype)
        self.wgs = tune['wgs']
        program = accel.build(context, "fill.mako", {
                'wgs': self.wgs,
                'ctype': ctype})
        self.kernel = program.get_kernel("fill")

    @classmethod
    @tune.autotuner
    def autotune(cls, context, dtype, ctype):
        queue = context.create_tuning_command_queue()
        shape = (1048576,)
        data = accel.DeviceArray(context, shape, dtype=dtype)
        def generate(wgs):
            fn = cls(context, dtype, ctype, {'wgs': wgs}).instantiate(queue, shape)
            fn.bind(data=data)
            def measure(iters):
                queue.start_tuning()
                for i in range(iters):
                    fn(123)
                return queue.stop_tuning() / iters
            return measure

        return tune.autotune(generate, wgs=[64, 128, 256, 512])

    def instantiate(self, command_queue, shape):
        return Fill(self, command_queue, shape)

class Fill(accel.Operation):
    """Concrete instance of :class:`FillTemplate`.

    .. rubric:: Slots

    **data**
        Array to be filled (padding will be filled too)

    Parameters
    ----------
    template : :class:`FillTemplate`
        Operation template
    command_queue : :class:`katsdpsigproc.cuda.CommandQueue` or :class:`katsdpsigproc.opencl.CommandQueue`
        Command queue for the operation
    shape : tuple of int
        Shape for the data slot
    """

    def __init__(self, template, command_queue, shape):
        super(Fill, self).__init__(command_queue)
        self.template = template
        self.shape = shape
        self.slots['data'] = accel.IOSlot(shape, self.template.dtype)

    def __call__(self, value, **kwargs):
        self.bind(**kwargs)
        self.check_all_bound()
        data = self.slots['data'].buffer

        elements = np.product(data.padded_shape)
        global_size = accel.roundup(elements, self.template.wgs)
        self.command_queue.enqueue_kernel(
                self.template.kernel,
                [data.buffer, np.uint32(elements), self.template.dtype.type(value)],
                global_size=(global_size,),
                local_size=(self.template.wgs,))
