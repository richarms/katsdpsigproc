#!groovy

def katsdp = fileLoader.fromGit('jenkins/scripts/katsdp.groovy', 'git@github.com:ska-sa/katsdpinfrastructure', 'jenkins2', 'katpull', '')
katsdp.standardBuild(maintainer: 'bmerry@ska.ac.za', opencl: true, cuda: true)
