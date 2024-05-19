"""Tests for the Google Generative AI Conversation integration conversation platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from google.api_core.exceptions import ClientError
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, intent

from tests.common import MockConfigEntry


@pytest.mark.parametrize(
    "agent_id", [None, "conversation.google_generative_ai_conversation"]
)
async def test_default_prompt(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component,
    area_registry: ar.AreaRegistry,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
    agent_id: str | None,
) -> None:
    """Test that the default prompt works."""
    entry = MockConfigEntry(title=None)
    entry.add_to_hass(hass)
    for i in range(3):
        area_registry.async_create(f"{i}Empty Area")

    if agent_id is None:
        agent_id = mock_config_entry.entry_id

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "1234")},
        name="Test Device",
        manufacturer="Test Manufacturer",
        model="Test Model",
        suggested_area="Test Area",
    )
    for i in range(3):
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", f"{i}abcd")},
            name="Test Service",
            manufacturer="Test Manufacturer",
            model="Test Model",
            suggested_area="Test Area",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "5678")},
        name="Test Device 2",
        manufacturer="Test Manufacturer 2",
        model="Device 2",
        suggested_area="Test Area 2",
    )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "9876")},
        name="Test Device 3",
        manufacturer="Test Manufacturer 3",
        model="Test Model 3A",
        suggested_area="Test Area 2",
    )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "qwer")},
        name="Test Device 4",
        suggested_area="Test Area 2",
    )
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "9876-disabled")},
        name="Test Device 3",
        manufacturer="Test Manufacturer 3",
        model="Test Model 3A",
        suggested_area="Test Area 2",
    )
    device_registry.async_update_device(
        device.id, disabled_by=dr.DeviceEntryDisabler.USER
    )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "9876-no-name")},
        manufacturer="Test Manufacturer NoName",
        model="Test Model NoName",
        suggested_area="Test Area 2",
    )
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "9876-integer-values")},
        name=1,
        manufacturer=2,
        model=3,
        suggested_area="Test Area 2",
    )
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_chat = AsyncMock()
        mock_model.return_value.start_chat.return_value = mock_chat
        chat_response = MagicMock()
        mock_chat.send_message_async.return_value = chat_response
        chat_response.parts = ["Hi there!"]
        chat_response.text = "Hi there!"
        result = await conversation.async_converse(
            hass,
            "hello",
            None,
            Context(),
            agent_id=agent_id,
        )

    assert result.response.response_type == intent.IntentResponseType.ACTION_DONE
    assert result.response.as_dict()["speech"]["plain"]["speech"] == "Hi there!"
    assert [tuple(mock_call) for mock_call in mock_model.mock_calls] == snapshot


async def test_error_handling(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_init_component
) -> None:
    """Test that client errors are caught."""
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_chat = AsyncMock()
        mock_model.return_value.start_chat.return_value = mock_chat
        mock_chat.send_message_async.side_effect = ClientError("some error")
        result = await conversation.async_converse(
            hass, "hello", None, Context(), agent_id=mock_config_entry.entry_id
        )

    assert result.response.response_type == intent.IntentResponseType.ERROR, result
    assert result.response.error_code == "unknown", result
    assert result.response.as_dict()["speech"]["plain"]["speech"] == (
        "Sorry, I had a problem talking to Google Generative AI: None some error"
    )


async def test_blocked_response(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_init_component
) -> None:
    """Test response was blocked."""
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_chat = AsyncMock()
        mock_model.return_value.start_chat.return_value = mock_chat
        chat_response = MagicMock()
        mock_chat.send_message_async.return_value = chat_response
        chat_response.parts = []
        result = await conversation.async_converse(
            hass, "hello", None, Context(), agent_id=mock_config_entry.entry_id
        )

    assert result.response.response_type == intent.IntentResponseType.ERROR, result
    assert result.response.error_code == "unknown", result
    assert result.response.as_dict()["speech"]["plain"]["speech"] == (
        "Sorry, I had a problem talking to Google Generative AI. Likely blocked"
    )


async def test_template_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that template error handling works."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            "prompt": "talk like a {% if True %}smarthome{% else %}pirate please.",
        },
    )
    with (
        patch(
            "google.generativeai.get_model",
        ),
        patch("google.generativeai.GenerativeModel"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        result = await conversation.async_converse(
            hass, "hello", None, Context(), agent_id=mock_config_entry.entry_id
        )

    assert result.response.response_type == intent.IntentResponseType.ERROR, result
    assert result.response.error_code == "unknown", result


async def test_conversation_agent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component,
) -> None:
    """Test GoogleGenerativeAIAgent."""
    agent = conversation.get_agent_manager(hass).async_get_agent(
        mock_config_entry.entry_id
    )
    assert agent.supported_languages == "*"
