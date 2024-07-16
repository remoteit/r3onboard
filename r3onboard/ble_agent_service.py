from dbus_next.service import ServiceInterface, method
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
import logging


class BleAgentService:
    class Agent(ServiceInterface):
        def __init__(self) -> None:
            super().__init__("org.bluez.Agent1")
            self.logger = logging.getLogger(name=__name__)

        @method()
        def RequestConfirmation(self, device: "o", passkey: "u"):  # type: ignore
            self.logger.info(f"RequestConfirmation ({device}, {passkey})")

    def __init__(self) -> None:
        self.logger = logging.getLogger(name=__name__)
        self.bus: MessageBus
        self.agent: BleAgentService.Agent

    async def unregister_all_agents(self) -> None:
        try:
            introspection = await self.bus.introspect("org.bluez", "/org/bluez")
            obj = self.bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
            manager = obj.get_interface("org.bluez.AgentManager1")
            await manager.call_unregister_agent("/org/bluez/anAgent")  # type: ignore
            self.logger.info("Existing agent unregistered")
        except Exception as e:
            self.logger.info(f"No existing agent to unregister: {e}")

    async def register_agent(self) -> None:
        self.logger.info("Registering agent...")
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        # name_request_reply = await self.bus.request_name("it.remote.AgentService")
        # self.logger.info(f"Bus name: {self.bus.unique_name}")

        self.agent = self.Agent()
        export_response = self.bus.export("/it/remote/BleAgent", self.agent)
        self.logger.info(f"Export response: {export_response}")

        introspection = await self.bus.introspect("org.bluez", "/org/bluez")
        obj = self.bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
        manager = obj.get_interface("org.bluez.AgentManager1")

        register_response = await manager.call_register_agent("/it/remote/BleAgent", "DisplayYesNo")  # type: ignore
        self.logger.info(f"Register response: {register_response}")


# Example usage
# async def main():
#     ble_agent_service = BleAgentService()
#     await ble_agent_service.register_agent()


# asyncio.run(main())
