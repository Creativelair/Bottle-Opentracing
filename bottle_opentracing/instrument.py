import opentracing
from bottle import default_app
from signalfx_tracing import utils
from wrapt import wrap_function_wrapper

from bottle_opentracing import BottleTracing

config = utils.Config(
    trace_all=True,
    traced_attributes=['path', 'method'],
    tracer=None,
)


def instrument(tracer=None):
    bottle = utils.get_module('bottle')
    if utils.is_instrumented(bottle):
        return

    def bottle_tracer(run, _, args, kwargs):
        """
        A function wrapper of bottle.run to create a corresponding
        BottleTracer upon app instantiation.
        """
        app = kwargs.get('app', default_app())
        _tracer = tracer or config.tracer or opentracing.tracer
        BottleTracing(tracer=_tracer, trace_all_requests=config.trace_all,
                      app=app, traced_attributes=config.traced_attributes)

        run(**kwargs)

    wrap_function_wrapper('bottle', 'run', bottle_tracer)
    utils.mark_instrumented(bottle)


def uninstrument():
    """
    Will only prevent new applications from registering tracers.
    It's not reasonably feasible to remove existing before/after_request
    trace methods of existing apps.
    """
    bottle = utils.get_module('bottle')
    if not utils.is_instrumented(bottle):
        return

    utils.revert_wrapper(bottle, 'run')
    utils.mark_uninstrumented(bottle)
