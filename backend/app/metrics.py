"""Low-cardinality business metrics for the interview workflow."""

from opentelemetry.metrics import Meter


class ApplicationMetrics:
    def __init__(self, meter: Meter) -> None:
        self.interview_rooms_created = meter.create_counter(
            "blueprint.interview.rooms.created",
            unit="{room}",
            description="Interview rooms created successfully.",
        )
        self.active_participants = meter.create_up_down_counter(
            "blueprint.interview.participants.active",
            unit="{participant}",
            description="Participants currently connected to interview rooms.",
        )
        self.canvas_elements_created = meter.create_counter(
            "blueprint.canvas.elements.created",
            unit="{element}",
            description="New unique canvas elements persisted successfully.",
        )
        self.component_creation_errors = meter.create_counter(
            "blueprint.canvas.component_creation.errors",
            unit="{error}",
            description="Failed canvas component persistence operations.",
        )
