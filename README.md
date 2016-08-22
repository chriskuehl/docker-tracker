docker-tracker
--------

docker-tracker is proof-of-concept code that makes it easy to track and kill
the Docker containers launched by a process.

An example use case is in CI environments where each project's tests spawn
several Docker containers. In an ideal world, the project would properly clean
up the containers it started. However, in the real world we know this won't
always happen, as there are many potential failure cases and inevitably
containers will eventually leak even after the test run has failed and the
processes which spawned them have ended.

docker-tracker works by proxying requests to and from the primary Docker
socket. The tests always talk to docker-tracker, which allows it to record the
IDs of spawned containers.


### Usage

The intended usage is like this:

1. **In the pre-test phase.** Start `docker-tracker`.

2. **In the test phase.** Run your tests with `DOCKER_HOST=localhost:[port]`,
   using the port you started it on.

3. **In the post-test phase.** Kill the containers with a command like
   `curl http://localhost:[port]/tracker | xargs -n1 docker kill`,
   then kill the tracker itself.

I wonder if this could be made into a Jenkins plugin?


### Installation

Make a Python 2.7 virtualenv, install `twisted==16.3.2`), and run `tracker.py
--help`.


### Example session

```bash
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ ./tracker.py -p 8080 &
Listening on port 8080...
[1] 2938916
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ export DOCKER_HOST=localhost:8080
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ docker run -d debian:jessie bash -c 'while :; do true; done'
bb7a1624199fa31025bf6548def02b0b225c7a78f3e7187b08541647181cfd70
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ docker run -d debian:jessie bash -c 'while :; do true; done'
a903acb30fd0a153a584c5593609a5100e98845fa368bb4d77ce8c179b7fbe55
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ docker run -d debian:jessie bash -c 'while :; do true; done'
e20a7dccf89b7e6f36023f4677e0d977e96071d1041651ddc676f98ad8bb024a
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ curl http://localhost:8080/tracker
a903acb30fd0a153a584c5593609a5100e98845fa368bb4d77ce8c179b7fbe55
bb7a1624199fa31025bf6548def02b0b225c7a78f3e7187b08541647181cfd70
e20a7dccf89b7e6f36023f4677e0d977e96071d1041651ddc676f98ad8bb024a
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ curl http://localhost:8080/tracker | xargs -n1 docker kill
a903acb30fd0a153a584c5593609a5100e98845fa368bb4d77ce8c179b7fbe55
bb7a1624199fa31025bf6548def02b0b225c7a78f3e7187b08541647181cfd70
e20a7dccf89b7e6f36023f4677e0d977e96071d1041651ddc676f98ad8bb024a
(venv) ckuehl@hydrogen:~/proj/docker-tracker$ kill %1
[1]  + done       ./tracker.py -p 8080
```


### Limitations

Currently this is not well-tested, but it seems to work reasonably well.

Some future work that might be interesting:

* **Logging Docker API calls.** It might be useful to see what jobs are doing
  for auditing or debugging.

* **Restricting capabilities and bind mounts.** Currently, Docker is basically
  free `root` on a machine. It would be possible to restrict access to the main
  Docker socket and only allow jobs to talk to the tracker, which does
  authorization (e.g. limiting which paths you can bind mount).

* **Binding to domain sockets.** Currently, this proof-of-concept wants to bind
  to a port on localhost. This is easy to test but fairly awkward in the
  real-world where a domain socket would be preferred. Should be an easy fix.

* **Python 2.7 only.** Python 3 would be nice, but I'm not smart enough to
  figure out how to use Twisted correctly.
