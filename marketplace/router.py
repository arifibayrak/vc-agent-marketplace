from marketplace import database, event_bus
from marketplace.registry import AgentRegistry
from models.message_models import MessageEnvelope


class MessageRouter:
    """Routes messages between agents through the marketplace."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def route(self, envelope: MessageEnvelope, recipient_id: str,
                    deal_id: str | None = None) -> bool:
        """Route a message to a specific agent. Logs the message and event."""
        # Persist message
        await database.save_message(
            message_id=envelope.message_id,
            deal_id=deal_id,
            message_type=envelope.message_type.value,
            sender_id=envelope.sender_id,
            recipient_id=recipient_id,
            payload=envelope.payload,
            correlation_id=envelope.correlation_id,
        )

        # Send to recipient
        sent_data = envelope.model_dump(mode="json")
        sent_data["recipient_id"] = recipient_id
        success = await self.registry.send_to(recipient_id, sent_data)

        sender = self.registry.get(envelope.sender_id)
        recipient = self.registry.get(recipient_id)
        sender_name = sender.name if sender else envelope.sender_id
        recipient_name = recipient.name if recipient else recipient_id

        if success:
            await event_bus.emit_marketplace_event(
                f"Routed: {envelope.message_type.value} from {sender_name} to {recipient_name}",
                deal_id=deal_id,
            )
        else:
            await event_bus.emit_marketplace_event(
                f"Failed to route {envelope.message_type.value} to {recipient_name}",
                deal_id=deal_id,
            )

        return success

    async def route_to_marketplace(self, envelope: MessageEnvelope,
                                   deal_id: str | None = None):
        """Log a message sent to the marketplace (no forwarding needed)."""
        await database.save_message(
            message_id=envelope.message_id,
            deal_id=deal_id,
            message_type=envelope.message_type.value,
            sender_id=envelope.sender_id,
            recipient_id="marketplace",
            payload=envelope.payload,
            correlation_id=envelope.correlation_id,
        )
