"""Consumer-agnostic integration surface for embedding DeepTutor.

Five independent faces, none of which knows who is on the other side:

- external identity federation (one-time code exchange -> local session)
- external context handoff (opaque payload, associated with a session)
- embedded viewer configuration (iframe URL, origin, sandbox)
- ``ConversationEvent`` output (conversation facts, not interpretations)
- HTTP event sink with a persistent outbox (at-least-once delivery)

The rule this package exists to hold: DeepTutor may *carry* a host product's
data, but its source, contracts, and configuration keys must never encode what
that data means or who produced it.
"""

from deeptutor.integrations.external.config import (
    ExternalIntegrationConfig,
    get_external_config,
)
from deeptutor.integrations.external.models import (
    PROTOCOL_VERSION,
    ConversationEvent,
    ExternalContext,
    ExternalIdentity,
)
from deeptutor.integrations.external.sink import get_event_sink_worker
from deeptutor.integrations.external.store import get_external_store
from deeptutor.integrations.external.subscriber import (
    register_conversation_event_publisher,
    unregister_conversation_event_publisher,
)

__all__ = [
    "PROTOCOL_VERSION",
    "ConversationEvent",
    "ExternalContext",
    "ExternalIdentity",
    "ExternalIntegrationConfig",
    "get_event_sink_worker",
    "get_external_config",
    "get_external_store",
    "register_conversation_event_publisher",
    "unregister_conversation_event_publisher",
]
