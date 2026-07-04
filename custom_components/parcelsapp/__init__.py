from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.template import Template
import voluptuous as vol

from .const import DOMAIN, SERVICE_TRACK_PACKAGE, SERVICE_REMOVE_PACKAGE
from .coordinator import ParcelsAppCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.BUTTON]

# Schémas pour les services (support explicite des templates)
TRACK_PACKAGE_SCHEMA = vol.Schema({
    vol.Required("tracking_id"): vol.Any(cv.string, cv.template),
    vol.Optional("name"): vol.Any(cv.string, cv.template, None),
})

REMOVE_PACKAGE_SCHEMA = vol.Schema({
    vol.Required("tracking_id"): vol.Any(cv.string, cv.template),
})


async def _async_render_value(hass: HomeAssistant, value):
    """Render a value if it is a template string or Template object."""
    if isinstance(value, Template):
        return await hass.async_add_executor_job(
            value.async_render, variables={"hass": hass}
        )
    if isinstance(value, str) and ("{{" in value and "}}" in value):
        template = Template(value, hass)
        return await hass.async_add_executor_job(
            template.async_render, variables={"hass": hass}
        )
    return value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ParcelsAppCoordinator(hass, entry)
    await coordinator.async_init()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_track_package(call: ServiceCall) -> None:
        tracking_id = await _async_render_value(hass, call.data["tracking_id"])
        name = await _async_render_value(hass, call.data.get("name"))

        await coordinator.track_package(tracking_id, name)
        async_dispatcher_send(hass, f"{DOMAIN}_new_package", tracking_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_TRACK_PACKAGE,
        handle_track_package,
        schema=TRACK_PACKAGE_SCHEMA,
    )

    async def handle_remove_package(call: ServiceCall) -> None:
        tracking_id = await _async_render_value(hass, call.data["tracking_id"])
        await coordinator.remove_package(tracking_id)
        async_dispatcher_send(hass, f"{DOMAIN}_remove_package", tracking_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PACKAGE,
        handle_remove_package,
        schema=REMOVE_PACKAGE_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        unsub_dispatchers = hass.data[DOMAIN].pop(entry.entry_id + "_unsub_dispatcher", [])
        for unsub in unsub_dispatchers:
            unsub()
    return unload_ok
