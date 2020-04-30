# Bottle-OpenTracing

This package enables distributed tracing in Bottle applications via `The OpenTracing Project`.
It is heavily influenced by the [Flask Opentracing implementation](https://github.com/opentracing-contrib/python-flask).

Installation
============

Run the following command:

```
$ pip install Bottle-Opentracing
```

Usage
=====

This Bottle extension allows for tracing of Bottle apps using the OpenTracing API. All
that it requires is for a ``BottleTracing`` tracer to be initialized using an
instance of an OpenTracing tracer. You can either trace all requests to your site, or use function decorators to trace certain individual requests.

**Note:** `optional_args` in both cases are any number of attributes (as strings) of `bottle.Request` that you wish to set as tags on the created span

Initialize
----------

`BottleTracing` wraps the tracer instance that's supported by opentracing. To create a `BottleTracing` object, you can either pass in a tracer object directly or a callable that returns the tracer object. For example:

```python
import opentracing
from bottle_opentracing import BottleTracing

opentracing_tracer = ## some OpenTracing tracer implementation
tracing = BottleTracing(opentracing_tracer, ...)
```

or

```python
import opentracing
from bottle_opentracing import BottleTracing

def initialize_tracer():
    ...
    return opentracing_tracer

tracing = BottleTracing(initialize_tracer, ...)
```

Trace All Requests
------------------

```python
import opentracing
from bottle_opentracing import BottleTracing

app = bottle.app()

opentracing_tracer = ## some OpenTracing tracer implementation
tracing = BottleTracing(opentracing_tracer, True, app, [optional_args])
```

Trace Individual Requests
-------------------------

```python
import opentracing
from bottle_opentracing import BottleTracing

app = bottle.app()

opentracing_tracer = ## some OpenTracing tracer implementation  
tracing = BottleTracing(opentracing_tracer)

@app.get('/some_url')
@tracing.trace(optional_args)
def some_view_func():
	...     
	return some_view 
```

Accessing Spans Manually
------------------------

In order to access the span for a request, we've provided an method `BottleTracing.get_span(request)` that returns the span for the request, if it is exists and is not finished. This can be used to log important events to the span, set tags, or create child spans to trace non-RPC events. If no request is passed in, the current request will be used.

Tracing an RPC
--------------

If you want to make an RPC and continue an existing trace, you can inject the current span into the RPC. For example, if making an http request, the following code will continue your trace across the wire:

```python
@tracing.trace()
def some_view_func(request):
    new_request = some_http_request
    current_span = tracing.get_span(request)
    text_carrier = {}
    opentracing_tracer.inject(span, opentracing.Format.TEXT_MAP, text_carrier)
    for k, v in text_carrier.iteritems():
        new_request.add_header(k,v)
    ... # make request
```
