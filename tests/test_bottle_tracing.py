import unittest
from unittest.mock import patch

import bottle
import opentracing
from opentracing.ext import tags
from opentracing.mocktracer import MockTracer
from webtest import TestApp

from bottle_opentracing import BottleTracing

app = bottle.app()
test_app = TestApp(app)
after_hooks = app._hooks['after_request']

tracing_all = BottleTracing(MockTracer(), True, app, ['url'])
tracing = BottleTracing(MockTracer())
tracing_deferred = BottleTracing(lambda: MockTracer(), True, app, ['url'])


def flush_spans(tcr):
    for req in tcr._current_scopes:
        tcr._current_scopes[req].close()
    tcr._current_scopes = {}


@bottle.get('/test')
def check_test_works():
    return 'Success'


@bottle.get('/another_test')
@tracing.trace('url', 'url_rule')
def decorated_fn():
    return 'Success again'


@bottle.get('/another_test_simple')
@tracing.trace('query_string', 'is_xhr')
def decorated_fn_simple():
    return 'Success again'


@bottle.get('/error_test')
@tracing.trace()
def decorated_fn_with_error():
    raise RuntimeError('Should not happen')


@bottle.get('/decorated_child_span_test')
@tracing.trace()
def decorated_fn_with_child_span():
    with tracing.tracer.start_active_span('child'):
        return 'Success'


@bottle.get('/wire')
def send_request():
    span = tracing_all.get_span()
    headers = {}
    tracing_all.tracer.inject(span.context,
                              opentracing.Format.TEXT_MAP,
                              headers)
    test_app.get('/test', headers=headers)
    return ''


class TestTracing(unittest.TestCase):
    def setUp(self):
        tracing_all.tracer.reset()
        tracing.tracer.reset()
        tracing_deferred.tracer.reset()

    def test_span_creation(self):
        app._hooks['after_request'] = []

        test_app.get('/test')

        self.assertTrue(tracing_all.get_span(bottle.request))
        self.assertFalse(tracing.get_span(bottle.request))
        self.assertTrue(tracing_deferred.get_span(bottle.request))

        active_span = tracing_all.tracer.active_span
        self.assertIs(tracing_all.get_span(bottle.request), active_span)

        flush_spans(tracing_all)
        flush_spans(tracing_deferred)

    def test_span_deletion(self):
        app._hooks['after_request'] = after_hooks

        self.assertFalse(tracing_all._current_scopes)
        self.assertFalse(tracing_deferred._current_scopes)
        test_app.get('/test')
        self.assertFalse(tracing_all._current_scopes)
        self.assertFalse(tracing_deferred._current_scopes)

    def test_span_tags(self):
        test_app.get('/another_test_simple')

        spans = tracing.tracer.finished_spans()
        self.assertEqual(1, len(spans))
        self.assertEqual(spans[0].tags, {
            tags.COMPONENT: 'Bottle',
            tags.HTTP_METHOD: 'GET',
            tags.SPAN_KIND: tags.SPAN_KIND_RPC_SERVER,
            tags.HTTP_URL: 'http://localhost:80/another_test_simple',
            tags.HTTP_STATUS_CODE: 200,
            'is_xhr': 'False',
        })

    def test_requests_distinct(self):
        app._hooks['after_request'] = []

        test_app.get('/test')

        second_scope = tracing_all._current_scopes.pop(bottle.request)
        self.assertTrue(second_scope)
        second_scope.close()
        self.assertFalse(tracing_all.get_span(bottle.request))

        flush_spans(tracing_all)
        flush_spans(tracing_deferred)

    def test_decorator(self):
        app._hooks['after_request'] = []

        test_app.get('/another_test')

        self.assertFalse(tracing.get_span(bottle.request))
        self.assertEqual(1, len(tracing_deferred._current_scopes))
        self.assertEqual(1, len(tracing_all._current_scopes))

        active_span = tracing_all.tracer.active_span
        self.assertIs(tracing_all.get_span(bottle.request), active_span)

        flush_spans(tracing)
        flush_spans(tracing_all)
        flush_spans(tracing_deferred)

        app._hooks['after_request'] = after_hooks

        test_app.get('/another_test')

        self.assertFalse(tracing_all._current_scopes)
        self.assertFalse(tracing._current_scopes)
        self.assertFalse(tracing_deferred._current_scopes)

    def test_decorator_trace_all(self):
        # Fake we are tracing all, which should disable
        # tracing through our decorator.
        with patch.object(tracing, '_trace_all_requests', new=True):
            rv = test_app.get('/another_test_simple')
            self.assertTrue('200' in str(rv.status_code))

        spans = tracing.tracer.finished_spans()
        self.assertEqual(0, len(spans))

    def test_over_wire(self):
        rv = test_app.get('/wire')
        self.assertTrue('200' in str(rv.status_code))

        spans = tracing_all.tracer.finished_spans() + [tracing_all.tracer.active_span]
        self.assertEqual(2, len(spans))
        self.assertEqual(spans[0].context.trace_id, spans[1].context.trace_id)
        self.assertEqual(spans[0].parent_id, spans[1].context.span_id)

    def test_child_span(self):
        rv = test_app.get('/decorated_child_span_test')
        self.assertTrue('200' in str(rv.status_code))

        spans = tracing.tracer.finished_spans()
        self.assertEqual(2, len(spans))
        self.assertEqual(spans[0].context.trace_id, spans[1].context.trace_id)
        self.assertEqual(spans[0].parent_id, spans[1].context.span_id)


class TestTracingStartSpanCallback(unittest.TestCase):
    def test_simple(self):
        def start_span_cb(span, request):
            span.set_tag('component', 'not-bottle')
            span.set_tag('mytag', 'myvalue')

        tracing = BottleTracing(MockTracer(), True, app, start_span_cb=start_span_cb)
        rv = test_app.get('/test')
        self.assertTrue('200' in str(rv.status_code))

        spans = tracing.tracer.finished_spans()
        self.assertEqual(1, len(spans))
        self.assertEqual(spans[0].tags.get(tags.COMPONENT, None), 'not-bottle')
        self.assertEqual(spans[0].tags.get('mytag', None), 'myvalue')

    def test_error(self):
        def start_span_cb(span, request):
            raise RuntimeError('Should not happen')

        tracing = BottleTracing(MockTracer(), True, app, start_span_cb=start_span_cb)
        rv = test_app.get('/test')
        self.assertTrue('200' in str(rv.status_code))

        spans = tracing.tracer.finished_spans()
        self.assertEqual(1, len(spans))
        self.assertIsNone(spans[0].tags.get(tags.ERROR, None))
