"""
Radio Task:

Manages all radio communication for the cubesat.
"""
from lib.template_task import Task
import lib.transmission_queue as tq
import cdh

ANTENNA_ATTACHED = False

def should_transmit():
    """
    Return if we should transmit
    """
    return ANTENNA_ATTACHED

class task(Task):
    name = 'radio'
    color = 'teal'
    super_secret_code = b'p\xba\xb8C'

    cmd_dispatch = {
        'no-op':        cdh.noop,
        'hreset':       cdh.hreset,
        'shutdown':     cdh.shutdown,
        'query':        cdh.query,
        'exec_cmd':     cdh.exec_cmd,
    }

    def __init__(self, satellite):
        # Copy pasted from beacon_task.py, not sure about the purpose
        # Or if we need it for our protocol.
        super().__init__(satellite)
        # set our radiohead node ID so we can get ACKs
        self.cubesat.radio.node = 0xAB  # our ID
        self.cubesat.radio.destination = 0xBA  # target's ID

    async def main_task(self):
        if tq.empty():
            self.debug("No packets to send")
            self.cubesat.radio.listen()
            heard_something = await self.cubesat.radio.await_rx(timeout=10)
            if heard_something:
                response = self.cubesat.radio.receive(keep_listening=True, with_ack=ANTENNA_ATTACHED)
                if response is not None:
                    self.debug(f'Recieved msg "{response}", RSSI: {self.cubesat.radio.last_rssi - 137}')
                    # Processing recieved messages goes here
                    #  - Execute commands
                    #  - Mark messages as received (and remove from tq)

                    # Begin Old Beacon Task Code
                    if len(response) >= 6:
                        if not ANTENNA_ATTACHED:
                            self.debug('Antenna not attached. Skipping over-the-air command handling')
                        else:
                            if response[:4] == self.super_secret_code:
                                cmd = bytes(response[4:6])  # [pass-code(4 bytes)] [cmd 2 bytes] [args]
                                cmd_args = None
                                if len(response) > 6:
                                    self.debug('command with args', 2)
                                    try:
                                        cmd_args = response[6:]  # arguments are everything after
                                        self.debug(f'cmd args: {cmd_args}', 2)
                                    except Exception as e:
                                        self.debug(f'arg decoding error: {e}', 2)
                                if cmd in cdh.commands:
                                    try:
                                        if cmd_args is None:
                                            self.debug(f'running {cdh.commands[cmd]} (no args)')
                                            self.cmd_dispatch[cdh.commands[cmd]](self)
                                        else:
                                            self.debug(f'running {cdh.commands[cmd]} (with args: {cmd_args})')
                                            self.cmd_dispatch[cdh.commands[cmd]](self, cmd_args)
                                    except Exception as e:
                                        self.debug(f'something went wrong: {e}')
                                        self.cubesat.radio.send(str(e).encode())
                                else:
                                    self.debug('invalid command!')
                                    self.cubesat.radio.send(b'invalid cmd' + response[4:])
                    # End Old Beacon Task Code
            else:
                self.debug('No packets received')
        elif should_transmit():
            msg = tq.peek()
            packet, with_ack = msg.packet()
            self.debug(f'Transmission Queue {tq.queue}')
            short_packet = str(packet)[:20] + "...." if len(packet) > 23 else packet
            self.debug(f"Sending packet: {short_packet}")
            if with_ack:
                if self.cubesat.radio.send_with_ack(packet):
                    msg.ack()
                else:
                    msg.no_ack()
            else:
                self.cubesat.radio.send(packet, keep_listening=True)

            if tq.peek().done():
                tq.pop()
        self.cubesat.radio.sleep()
