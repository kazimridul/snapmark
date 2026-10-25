"""ScreenCast portal session owned by the recording worker's asyncio loop."""
import asyncio
import os
import uuid
from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus

DEST = 'org.freedesktop.portal.Desktop'
ROOT = '/org/freedesktop/portal/desktop'
IFACE = 'org.freedesktop.portal.ScreenCast'

class Portal:
    def __init__(self, cancelled):
        self.cancelled = cancelled
        self.bus = None
        self.session = None
        self.fd = None
        self.closed = False

    async def call(self, member, signature, body, interface=IFACE, path=ROOT):
        reply = await asyncio.wait_for(self.bus.call(Message(destination=DEST, path=path, interface=interface, member=member, signature=signature, body=body)), 15)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError('Desktop recording portal: ' + '; '.join(map(str, reply.body)))
        return reply

    async def request(self, member, signature, body):
        token = 'snapmark_' + uuid.uuid4().hex
        sender = self.bus.unique_name[1:].replace('.', '_')
        expected = f'{ROOT}/request/{sender}/{token}'
        future = asyncio.get_running_loop().create_future()
        def response(message):
            if message.path == expected and message.interface == 'org.freedesktop.portal.Request' and message.member == 'Response' and not future.done():
                future.set_result(message.body)
        self.bus.add_message_handler(response)
        body[-1]['handle_token'] = Variant('s', token)
        try:
            reply = await self.call(member, signature, body)
            expected = reply.body[0]
            deadline = asyncio.get_running_loop().time()+180
            while not future.done():
                if self.cancelled.is_set() or asyncio.get_running_loop().time() > deadline:
                    await self.call('Close', '', [], 'org.freedesktop.portal.Request', expected)
                    raise RuntimeError('Recording selection cancelled.')
                await asyncio.sleep(.1)
            code, values = future.result()
            if code:
                raise RuntimeError('Recording permission was cancelled or denied by the desktop.')
            return values
        finally:
            self.bus.remove_message_handler(response)

    async def open(self, mode):
        self.bus = await MessageBus(negotiate_unix_fd=True).connect()
        await self.bus.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus', interface='org.freedesktop.DBus', member='AddMatch', signature='s', body=["type='signal',interface='org.freedesktop.portal.Request',member='Response'"]))
        def closed(message):
            if message.path == self.session and message.interface == 'org.freedesktop.portal.Session' and message.member == 'Closed':
                self.closed = True
        self.bus.add_message_handler(closed)
        values = await self.request('CreateSession', 'a{sv}', [{'session_handle_token': Variant('s', 'snapmark_'+uuid.uuid4().hex)}])
        self.session = values['session_handle'].value
        await self.request('SelectSources', 'oa{sv}', [self.session, {'types': Variant('u', 2 if mode == 'window' else 1), 'multiple': Variant('b', False)}])
        values = await self.request('Start', 'osa{sv}', [self.session, '', {}])
        streams = values.get('streams')
        if not streams or not streams.value:
            raise RuntimeError('The portal returned no screen stream.')
        await self.open_remote()
        return self.fd, streams.value[0][0]

    async def open_remote(self):
        """A new PipeWire protocol connection for preview -> recording transition."""
        reply = await self.call('OpenPipeWireRemote', 'oa{sv}', [self.session, {}])
        if not reply.unix_fds:
            raise RuntimeError('The portal did not provide a PipeWire connection.')
        previous = self.fd
        self.fd = reply.unix_fds[reply.body[0]]
        if previous is not None:
            os.close(previous)
        return self.fd

    async def close(self):
        if self.bus:
            try:
                if self.session and not self.closed:
                    await self.call('Close', '', [], 'org.freedesktop.portal.Session', self.session)
            finally:
                if self.fd is not None:
                    os.close(self.fd)
                self.bus.disconnect()
