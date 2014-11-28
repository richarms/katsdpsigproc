import time
import numpy as np
from katsdpsigproc import accel
from katsdpsigproc.accel import DeviceArray, build

context = accel.create_some_context(True)
queue = context.create_command_queue(profile=True)


def gpu_percentile(context, queue, data):
    data = np.asarray(data, dtype=np.float32)
    N = data.shape[0]
    data_d = accel.DeviceArray(context, shape=data.shape, dtype=np.float32)
    data_d.set(queue, data)
    out_d = accel.DeviceArray(context, shape=(5,), dtype=np.float32)
    queue.enqueue_kernel(
            kernel,
            [data_d.buffer, out_d.buffer, np.int32(N)],
            global_size=(size,),
            local_size=(size,))
    out = out_d.empty_like()
    out_d.get(queue, out)
    return out

start_event = queue.enqueue_marker()

size = 128  # Number of workitems

_program = build(context, 'percentile.mako', {'size': size})
kernel = _program.get_kernel('test_percentile5_float')

data=np.abs(np.random.randn(400000))

t0=time.time()
out=gpu_percentile(context, queue, data)
t1=time.time()
expected = np.percentile(data,[0,100,25,75,50],interpolation='lower')
t2=time.time()
print 'out time',t1-t0
print 'out',out.astype(np.float32)
print 'exp time',t2-t1
print 'exp',expected.astype(np.float32)

odata=data+0
end_event = queue.enqueue_marker()
queue.finish()
