from typing import List, Callable

import bottle
import opentracing
from opentracing import Format
from opentracing.ext import tags


class BottleTracing(opentracing.Tracer):
    """
    Tracer that can trace certain requests to a Bottle app.

    @param tracer the OpenTracing tracer implementation to trace requests with
    """

    def __init__(self, tracer: opentracing.Tracer = None, trace_all_requests: bool = None, app: bottle.Bottle = None,
                 traced_attributes: List[str] = None, start_span_cb: Callable = None):

        if traced_attributes is None:
            traced_attributes = []

        if start_span_cb is not None and not callable(start_span_cb):
            raise ValueError('start_span_cb is not callable')

        if trace_all_requests is True and app is None:
            raise ValueError('trace_all_requests=True requires an app object')

        if trace_all_requests is None:
            trace_all_requests = False if app is None else True

        if not callable(tracer):
            self.__tracer = tracer
            self.__tracer_getter = None
        else:
            self.__tracer = None
            self.__tracer_getter = tracer

        self._trace_all_requests = trace_all_requests
        self._start_span_cb = start_span_cb
        self._current_scopes = {}

        # tracing all requests requires that app != None
        if self._trace_all_requests:
            app.add_hook('before_request', lambda: self._before_request_fn(traced_attributes))
            app.add_hook('after_request', lambda: self._after_request_fn())

    @property
    def tracer(self):
        if not self.__tracer:
            if self.__tracer_getter is None:
                return opentracing.tracer

            self.__tracer = self.__tracer_getter()

        return self.__tracer

    def trace(self, *attributes):
        """
        Function decorator that traces functions

        NOTE: Must be placed after the @bottle.* decorator

        @param attributes any number of bottle.Request attributes
        (strings) to be set as tags on the created span
        """

        def decorator(f):
            def wrapper(*args, **kwargs):
                if self._trace_all_requests:
                    return f(*args, **kwargs)

                self._before_request_fn(list(attributes))
                try:
                    r = f(*args, **kwargs)
                    self._after_request_fn()
                except Exception as e:
                    self._after_request_fn(error=e)
                    raise

                self._after_request_fn()
                return r

            wrapper.__name__ = f.__name__
            return wrapper

        return decorator

    def get_span(self, request=None):
        """
        Returns the span tracing `request`, or the current request if
        `request==None`.

        If there is no such span, get_span returns None.

        @param request the request to get the span from
        """
        if request is None and bottle.request:
            request = bottle.request

        scope = self._current_scopes.get(request, None)
        return None if scope is None else scope.span

    def _before_request_fn(self, attributes):
        request = bottle.request
        operation_name = request.path
        headers = {}
        for k, v in request.headers.items():
            headers[k.lower()] = v

        try:
            span_context = self.tracer.extract(
                format=Format.HTTP_HEADERS,
                carrier=headers,
            )
            scope = self.tracer.start_active_span(
                operation_name=operation_name,
                child_of=span_context
            )
        except (opentracing.InvalidCarrierException,
                opentracing.SpanContextCorruptedException):
            scope = self.tracer.start_active_span(operation_name)

        self._current_scopes[request] = scope

        span = scope.span
        self.add_request_tags(span, request)

        for attr in attributes:
            if hasattr(request, attr):
                payload = getattr(request, attr)
                if payload not in ('', b''):
                    span.set_tag(attr, str(payload))

        self._call_start_span_cb(span, request)

    @staticmethod
    def add_request_tags(span, request):
        if span and request:
            span.set_tag(tags.COMPONENT, 'Bottle')
            span.set_tag(tags.HTTP_METHOD, request.method)
            span.set_tag(tags.HTTP_URL, request.url)
            span.set_tag(tags.SPAN_KIND, tags.SPAN_KIND_RPC_SERVER)

    def _after_request_fn(self):
        request = bottle.request
        response = bottle.response

        # the pop call can fail if the request is interrupted by a
        # `before_request` method so we need a default
        scope = self._current_scopes.pop(request, None)
        if scope is None:
            return

        if response is not None:
            self.add_response_tags(scope.span, response)

        scope.close()

    @staticmethod
    def add_response_tags(span, response):
        if span and response:
            span.set_tag(tags.HTTP_STATUS_CODE, response.status_code)

    def _call_start_span_cb(self, span, request):
        if self._start_span_cb is None:
            return

        try:
            self._start_span_cb(span, request)
        except Exception:
            pass
