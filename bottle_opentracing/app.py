import bottle
import opentracing
from bottle import Bottle
from opentracing.ext import tags

from bottle_opentracing import BottleTracing


class APMBottleApp(Bottle):
    def default_error_handler(self, res):
        self.handle_error(res)
        return super().default_error_handler(res)

    @classmethod
    def handle_error(cls, res):
        _tracer = opentracing.tracer
        if _tracer:
            request = bottle.request
            with _tracer.start_active_span(request.path):
                BottleTracing.add_request_tags(_tracer.active_span, request)
                BottleTracing.add_response_tags(_tracer.active_span, res)
                cls.notice_error(_tracer, res.exception)

    @classmethod
    def notice_error(cls, tracer, err: Exception):
        if tracer and tracer.active_span:
            tracer.active_span.set_tag(tags.ERROR, True)
            tracer.active_span.log_kv({
                'event': tags.ERROR,
                'error.object': err,
            })
