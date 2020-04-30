import unittest
from unittest.mock import patch

import bottle
import opentracing

from bottle_opentracing import BottleTracing


class TestValues(unittest.TestCase):
    def test_tracer(self):
        tracer = opentracing.Tracer()
        tracing = BottleTracing(tracer)
        self.assertIs(tracing.tracer, tracer)
        self.assertFalse(tracing._trace_all_requests)

    def test_global_tracer(self):
        tracing = BottleTracing()
        with patch('opentracing.tracer'):
            self.assertIs(tracing.tracer, opentracing.tracer)
            opentracing.tracer = object()
            self.assertIs(tracing.tracer, opentracing.tracer)

    def test_trace_all_requests(self):
        app = bottle.app()
        tracing = BottleTracing(app=app)
        self.assertTrue(tracing._trace_all_requests)

        tracing = BottleTracing(app=app, trace_all_requests=False)
        self.assertFalse(tracing._trace_all_requests)

    def test_trace_all_requests_no_app(self):
        # when trace_all_requests is True, an app object is *required*
        self.assertRaises(ValueError, lambda: BottleTracing(trace_all_requests=True))

    def test_start_span_invalid(self):
        self.assertRaises(ValueError, lambda: BottleTracing(start_span_cb=0))
