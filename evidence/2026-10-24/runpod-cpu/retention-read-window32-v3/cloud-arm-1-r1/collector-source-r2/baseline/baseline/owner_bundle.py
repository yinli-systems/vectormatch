"""Bind closed evidence to the sole frozen owner validator; no alternative policy logic."""
from common import require,sha,OWNER_VALIDATOR_SHA
from pathlib import Path
import cpu_event_fetch_abab as controller
from owner_poll_attestation import validate_owner_bundle

def verify(c,release,arm,read,identities):
    require(sha(Path(__file__).with_name('owner_poll_attestation.py'))==OWNER_VALIDATOR_SHA==release['ownerPollValidatorSha256'],
        'Unique constructed-owner validator changed')
    controller.configure_arm(c['arm'])
    require(c['serverDriverMaximumParkNs']==100000 and c['ownerPollMaximumParkNs']==controller.selected_owner_park_ns()==1000000
        and c['eventFetchCount']==controller.selected_event_page(),
        'Registered ABAB owner cap/constant node-driver cap differ')
    reg=read(arm/'registration.json');configuration=read(arm/'load/configuration.json');summary=read(arm/'load/load-result.json')
    controller.validate_selected_page_observations(release,reg,configuration,summary,read(arm/'load/admission-plan.json'),
        read(arm/'completion.json'),read(arm/'functional-result.json'))
    observations=read(arm/'load/transport-observations.json')
    require(isinstance(observations,list)and observations,'Actual measured owner transport observations required')
    return validate_owner_bundle(registration=reg,configuration=configuration,summary=summary,
        before=read(arm/'load/owner-before-close.json'),after=read(arm/'load/owner-after-close.json'),
        parent=identities['pilot-parent'],nodes={n:identities['window-8-node-'+str(n)]for n in(0,1,2)},
        expected_owner_cap=c['ownerPollMaximumParkNs'],expected_parent_arguments=controller.parent_argv(release),
        expected_node_arguments={n:controller.node_argv(release,8,n,reg)for n in(0,1,2)},
        node_idle_actuals={n:read(arm/('node-%d/idle-observations/idle-000.actual.json'%n))for n in(0,1,2)},
        parent_idle_actuals=[v['retentionIdlePolicy']for v in observations]
            +[summary['physicalOfferTape']['lastActualTransportObservation']['retentionIdlePolicy']])
