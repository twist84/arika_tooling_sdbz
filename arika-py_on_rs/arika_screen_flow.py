"""Shared preview navigation for original EU-beta game-screen applications.

This is a *viewer* graph, not a boot emulator. IDs and handoffs come from
recovered EE application requests; the guided order below is an editor
convenience and must never be represented as an original boot sequence.
"""
from arika_app_registry import resolve_app, registered_native_requests


# User-confirmed guided preview order (1..5), not the original app IDs.
# Demo Main is a separate inspector, not an assumed sixth boot screen.
SCREEN_SEQUENCE = (
    'warning', 'startup', 'title', 'press_start', 'main_menu',
)
SCREEN_TAB_ORDER = SCREEN_SEQUENCE + ('demo',)
SCREEN_LABELS = {
    'startup': 'Startup / Splash',
    'warning': 'Warning / Video Mode',
    'title': 'Title Screen',
    'demo': 'Demo Main (inspector)',
    'press_start': 'Press Start',
    'main_menu': 'Main menu',
}
SCREEN_APP_IDS = {
    'startup': 4, 'warning': 5, 'title': 2,
    'demo': 6, 'press_start': 3, 'main_menu': 42,
}

# Directed requests recovered from individual native app handlers. These
# do NOT mean the target factory has been run, nor that loading finished.
NATIVE_VIEW_ROUTES = {
    # Confirmed by user-observed screen order AND original ELF request ID.
    ('warning', 1): 'startup',
    ('press_start', 42): 'main_menu',
    ('title', 6): 'demo',          # ID 2 => 6, 0x3F89CC
    ('demo', 3): 'press_start',    # conditional native ID 6 -> ID 3 request
    ('press_start', 6): 'demo',    # 20-second attract transition
    ('main_menu', 3): 'press_start',  # main-menu cancel gate
}
# Non-factory display handoffs are separate from ELF app requests.
# The owner confirmed the visible screen sequence, not an EE call address.
OBSERVED_SCREEN_COMPLETIONS = {
    'startup': 'title',
}
USER_OBSERVED_INTERMEDIATE_ROUTE = {
    # The ELF shows Title => app ID 6 (CAppDemoMain). The visible
    # editor workflow goes to Press Start. DemoMain is still retained as
    # a distinct native inspector and not claimed to have run.
    ('title', 6): 'press_start',
}
UNRESOLVED_REQUESTS = {}


def screen_step(screen, offset):
    """Editor-only sequence. It does not claim native startup order."""
    if screen not in SCREEN_TAB_ORDER or type(offset) is not int:
        raise ValueError('unknown preview screen or invalid offset')
    if screen == 'demo':
        return None
    next_index = SCREEN_SEQUENCE.index(screen) + offset
    if 0 <= next_index < len(SCREEN_SEQUENCE):
        return SCREEN_SEQUENCE[next_index]
    return None


def native_request_sites(source, destination_id):
    """Exact-ELF literal JAL evidence; no proof that a factory executed.

    A conditional field-derived target does not have a *literal* argument
    site; it must be represented independently.
    """
    if source not in SCREEN_APP_IDS:
        raise ValueError('unknown screen role')
    source_app_id = SCREEN_APP_IDS[source]
    return tuple(edge['callsite'] for edge in
                 registered_native_requests(source_app_id, 'transition')
                 if (edge['target_id'] == destination_id and
                     edge['is_registered_destination']))


def native_dynamic_request_sites(source, destination_id):
    """Recover only exact-ELF conditional requests and their target choices."""
    if source not in SCREEN_APP_IDS:
        raise ValueError('unknown screen role')
    if type(destination_id) is not int or not 1 <= destination_id <= 47:
        raise ValueError('invalid native destination ID')
    source_app_id = SCREEN_APP_IDS[source]
    return tuple(
        edge['callsite'] for edge in
        registered_native_requests(source_app_id, 'transition')
        if (edge['target_id'] is None and
            edge['source_attribution_verified'] and
            destination_id in edge.get('target_candidates', ())))


def native_view_request(source, destination_id):
    """Describe a witnessed native request without executing any factory."""
    if source not in SCREEN_TAB_ORDER:
        raise ValueError('unsupported source screen')
    if type(destination_id) is not int or destination_id < 0:
        raise ValueError('invalid native application ID')
    target = NATIVE_VIEW_ROUTES.get((source, destination_id))
    app = resolve_app(destination_id)
    if target is not None:
        request_sites = native_request_sites(source, destination_id)
        dynamic_sites = native_dynamic_request_sites(source, destination_id)
        is_demo_exit = source == 'demo' and destination_id == 3
        if is_demo_exit:
            provenance = ('ELF-verified conditional DemoMain native request '
                          'from ID 6 to ID 3; original exit conditions '
                          'and actual factory execution are not observed')
        elif (source, destination_id) in (
                ('warning', 1), ('press_start', 42)):
            provenance = ('user-observed visual transition plus native '
                          'request ID')
        else:
            provenance = 'native ELF literal request with candidate source'
        source_app_id = SCREEN_APP_IDS[source]
        matching_requests = registered_native_requests(source_app_id,
                                                        'transition')
        source_verified = any(
            edge['source_attribution_verified']
            for edge in matching_requests
            if edge['target_id'] == destination_id) or bool(dynamic_sites)
        return {
            'source': source,
            'destination_id': destination_id,
            'destination': target,
            'verified_preview_route': True,
            'factory_executed': False,
            'native_request_sites': request_sites,
            'native_dynamic_request_sites': dynamic_sites,
            'native_literal_edge_confirmed': bool(request_sites),
            'native_dynamic_edge_confirmed': bool(dynamic_sites),
            'native_source_attribution_verified': source_verified,
            'provisional_parent_return': False,
            'native_source_class': resolve_app(source_app_id)['class_name'],
            'provenance': provenance,
            'app_class': app['class_name'] if app else None,
            'message': ('%s ID %d (%s). %s. Preview navigation only; '
                        'original game factory was NOT executed.' %
                        ('Conditional native request for' if is_demo_exit else
                         'Native request for',
                         destination_id, SCREEN_LABELS[target], provenance)),
        }
    detail = UNRESOLVED_REQUESTS.get(
        (source, destination_id),
        ('Native request for ID %d (%s) has no supported screen preview' %
         (destination_id,
          app['class_name'] if app is not None else 'unregistered app')))
    return {
        'source': source,
        'destination_id': destination_id,
        'destination': None,
        'verified_preview_route': False,
        'factory_executed': False,
        'message': detail + '; use manual preview navigation if needed.',
    }



def observed_screen_completion(source):
    """User-confirmed display handoff with no asserted EE factory call."""
    if source not in SCREEN_TAB_ORDER:
        raise ValueError('unsupported original screen')
    target = OBSERVED_SCREEN_COMPLETIONS.get(source)
    if target is None:
        return None
    return {
        'source': source,
        'destination': target,
        'destination_id': None,
        'provenance': 'user-observed visual screen sequence',
        'factory_executed': False,
        'message': ('Observed %s → %s screen progression; exact native '
                    'next-app callback not yet recovered.' %
                    (SCREEN_LABELS[source], SCREEN_LABELS[target])),
    }
