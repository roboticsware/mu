"""

This module is directly copied from

    https://github.com/roboticsware/nethelper

at revision ec99291a867e1e37431d62ef61c015ec31dc6667
and used under CC0.

"""
# flake8: noqa: E501
#!/usr/bin/env python3
'''
This module provides the NetNode class for simple game networking. It
can also be executed as a script to start the message relay server.
'''


# Socket data format
#
# Frame Length: 4 (binary)
# Version: 3
# Dest: 1       # 255 means "ALL". 255 is also used for msg to server.
# Sender: 1     # 0 means "SERVER", 255 means "UNKNOWN" (ie. I don't know my addr)
# Type: 1       # See "Data"
# Meta: 1       # Meaning depends on frame type.
# Data: json unless otherwise specified
#     = FRAME_TYPE_AUTH: 1
#     {
#       name: string, # Blank string to request server to assign a name
#       group: string
#     }
#
#     = FRAME_TYPE_DATA: 2 (Meta: 0)
#     [
#       {
#         title: string,
#         content: any,
#         queue: bool
#       },
#       ...
#     ]
#     Other meta may be used to indicate different data format (eg. compressed)
#
#     = FRAME_TYPE_HEART: 3
#     No data (ie. length = 0)
#
#     = FRAME_TYPE_PEERS: 4
#     [
#       {
#         name: string,
#         addr: int
#       },
#       ...
#     ]
#     List of connected devices. Sent by server on AUTH and on change.
#
#     = FRAME_TYPE_REQ: 5
#     {
#       type: int,
#       data: any
#     }
#     Request from client to server (eg. to get a list of peers)
#       type=0, data=None   : Disconnect
#       type=1, data=None   : Request peers list
#       type=2, data=String : Request name change. data contains name. (not implemented)
#
#     = FRAME_TYPE_SYSM: 6
#     {
#       type: int,
#       msg: string,
#       data: any
#     }
#     System messages. Only sent by server
#       type=0, msg=None, data=name (string) : Server assigned name.




import socket
import selectors
import json
import time
import argparse
import random
import inspect
import copy
from collections import OrderedDict
class Net:
    '''
    Base class for NetNode and NetServer. It should not be used on its
    own.
    '''

    HEADER_SIZE = 11
    VERSION = b'020'

    DEFAULT_PORT = 65042

    FRAME_TYPE_AUTH = b'\x01'
    FRAME_TYPE_DATA = b'\x02'
    FRAME_TYPE_HEART = b'\x03'
    FRAME_TYPE_PEERS = b'\x04'
    FRAME_TYPE_REQ = b'\x05'
    FRAME_TYPE_SYSM = b'\x06'

    SYSM_TYPE_NAME = 0

    REQ_TYPE_DISCONNECT = 0
    REQ_TYPE_PEERS = 1

    SERVER_ADDR = b'\x00'
    UNKNOWN_ADDR = b'\xff'
    ALL_CLIENTS = b'\xff'

    def _dumps(self, data):
        return bytes(json.dumps(data), 'utf-8')

    def _loads(self, data):
        return json.loads(data.decode('utf-8'))

    def _construct_frame(self, frame, b_data):
        frame_length = self.HEADER_SIZE + len(b_data)

        if 'meta' not in frame or frame['meta'] == None:
            frame['meta'] = b'\0'

        return (
            frame_length.to_bytes(4, 'big')
            + self.VERSION
            + frame['dest']
            + self.my_addr
            + frame['type']
            + frame['meta']
            + b_data
        )

    def _encode_frame(self, frame):
        if 'data' in frame:
            b_data = self._dumps(frame['data'])
        else:
            b_data = b''

        return self._construct_frame(frame, b_data)

    def _decode_frame(self, frame):
        decoded = {}

        decoded['version'] = frame[4:7]
        if decoded['version'] != self.VERSION:
            raise Exception('Error: Incompatible Nethelpher version',
                            decoded['version'])

        decoded['dest'] = frame[7:8]
        decoded['sender'] = frame[8:9]
        decoded['type'] = frame[9:10]
        decoded['meta'] = frame[10:11]
        decoded['data'] = frame[11:]

        return decoded

    def _get_frame(self, data):
        buf_size = len(data)
        if buf_size < self.HEADER_SIZE:
            return None, data

        frame_len = int.from_bytes(data[:4], 'big')
        if buf_size < frame_len:
            return None, data

        frame_bytes = data[:frame_len]
        remainder = data[frame_len:]

        return frame_bytes, remainder

#
# Client
#


class NetNode(Net):
    '''
    The NetNode object is used to communicate between nodes.
    You'll need to run "connect" after object creation to connect to a
    server.

    Returns:
        A NetNode object.
    '''

    IN_BUFFER_LIMIT = 102400
    OUT_BUFFER_LIMIT = 102400

    def __init__(self):
        self.inBuf = b''
        self.outBuf = b''
        self.heartBeatTime = time.time()
        self.in_data = {}
        self.out_data = {}
        self.peers = OrderedDict()
        self.my_addr = self.UNKNOWN_ADDR

    def connect(self, host, name, group, port=None, wait=True, timeout=5):
        '''
        Connect to the server.

        Args:
            host: A string specifying the IP or domain name of the server
              to connect to.
            name: A string providing the name of this node. You can use
              anything here. If a blank string is provided, the server will
              assign you a random name that you can later read using
              get_name().
            group: A string specifying the group that this node belongs to.
              It must be a valid group that the server recognises.
            port: An integer specifying the server port.
            wait: If True, wait until connected or until timeout is reached
              If False, return immediately.
            timeout: If still not connected after this time, exit this
              function.

        Returns:
            True if connected. False if timeout is reached. If wait is
            False, this will always return True.
        '''
        if port == None:
            port = self.DEFAULT_PORT

        self.name = name
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        self.socket.setblocking(False)
        self._send_auth(name, group)
        self.process_send()

        if wait:
            return self._wait_for_connection(timeout)

        return True

    def process_send(self):
        '''
        Send out all buffered data. You need to run this regularly (at
        least every 1 second) even if there are no data to transmit, or
        the node may be disconnected by the server.

        Returns:
            None
        '''
        for dest in self.out_data:
            if len(self.out_data[dest]) > 0:
                self._send_data_frame(dest, self.out_data[dest])
                self.out_data[dest] = []

        if self.outBuf:
            self.heartBeatTime = time.time()
            while len(self.outBuf):
                try:
                    sent = self.socket.send(self.outBuf)
                    self.outBuf = self.outBuf[sent:]
                except BlockingIOError:
                    break
        else:
            self._send_heartbeat_frame()

    def process_recv(self):
        '''
        Read all received data from the network buffer. You need to run
        this regularly.

        Returns:
            None
        '''
        while True:
            try:
                received = self.socket.recv(1024)
                if len(received) == 0:
                    break
                self.inBuf += received
            except BlockingIOError:
                break
        self._process_inbuf()

    def available(self, sender, title):
        '''
        Check if any messages are available to read.

        Args:
            sender: String specifying the sender to check.
            title: String specifying the message title to check.

        Returns:
            Number of messages available to read.
        '''

        if sender not in self.in_data:
            return 0
        if title not in self.in_data[sender]:
            return 0
        if len(self.in_data[sender][title]) < 1:
            return 0

        return len(self.in_data[sender][title])

    def get_msg(self, sender, title, clear=True):
        '''
        Get the oldest message from the queue.

        Args:
            sender: String specifying the sender to check.
            title: String specifying the message title to check.
            clear: If False, the message will not be removed from queue.

        Returns:
            One message.
        '''
        if sender not in self.in_data:
            return None
        if title not in self.in_data[sender]:
            return None
        if len(self.in_data[sender][title]) < 1:
            self.in_data[sender].pop(title)
            return None

        if clear:
            return self.in_data[sender][title].pop(0)
        else:
            return self.in_data[sender][title][0]

    def get_all_msgs(self, sender, title, clear=True):
        '''
        Get the all messages from the queue.

        Args:
            sender: String specifying the sender to check.
            title: String specifying the message title to check.
            clear: If False, the messages will not be removed from queue.

        Returns:
            A list of all messages in the queue.
        '''
        if sender not in self.in_data:
            return None
        if title not in self.in_data[sender]:
            return None
        if len(self.in_data[sender][title]) < 1:
            self.in_data[sender].pop(title)
            return None

        if clear:
            tmp = self.in_data[sender][title]
            self.in_data[sender][title] = []
            return tmp
        else:
            return self.in_data[sender][title]

    def send_msg(self, name, title, content, queue=False):
        '''
        Send a message to the output buffer. The message will only be
        transmitted when process_send() is executed. This function will
        make a shallow copy of the content.

        Args:
            name: String specifying the recipient name, or "ALL" to send
              to all nodes in the group.
            title: String specifying the message title. This can be
              anything, but it is good practice to use the variable name of
              the content.
            content: The content to be sent. Anything that can be converted
              to JSON can be used (eg. numbers, string, list, dict).
            queue: If set to True, the message will be queued at the
              recipient. If set to False, the latest message will always
              overwrite any unread messages.

        Returns:
            True if message was successfully sent to the output buffer.
            False if the recipient name is not valid.
        '''
        dest = self._get_peer_addr(name)
        if dest == None:
            return False

        data = {
            'title': title,
            'content': copy.copy(content),
            'queue': queue
        }

        if dest not in self.out_data:
            self.out_data[dest] = []
        self.out_data[dest].append(data)

        return True

    def share_variables(self, name, variables):
        '''
        Share all variables using the provided list of names. Variables
        can be local or global. Variables sent using this function is
        never queued. This function is magical; learners should avoid it.

        Args:
            name: String specifying the recipient name, or "ALL" to send
              to all nodes in the group.
            variables: List of strings specifying the variables to be
              shared.
        '''
        frame = inspect.currentframe()
        for variable in variables:
            try:
                if variable in frame.f_back.f_locals:
                    value = frame.f_back.f_locals[variable]
                elif variable in frame.f_back.f_globals:
                    value = frame.f_back.f_globals[variable]
                else:
                    raise KeyError('Variable ' + str(variable) + ' not found')
                self.send_msg(name, variable, value, queue=False)
            finally:
                del frame

    def update_globals(self, name, variables):
        '''
        Update globals variables using the provided list of names.
        Variables must be global. This function is magical; learners
        should avoid it.

        Args:
            name: String specifying the sender name.
            variables: List of strings specifying the variables to be
              updated.
        '''
        frame = inspect.currentframe()
        for variable in variables:
            try:
                if variable in frame.f_back.f_globals:
                    value = self.get_msg(name, variable)
                    if value is not None:
                        frame.f_back.f_globals[variable] = value
                else:
                    raise KeyError('Variable ' + str(variable) + ' not a global')
            finally:
                del frame

    def get_peers(self):
        '''
        Get a list of nodes currently connected to the same group.

        Returns:
            A list of string containing the names of nodes.
        '''
        return list(self.peers.keys())

    def get_name(self):
        '''
        Get the name of this node.
        This is used to find out your own node name if you are requesting
        the server to issue you a random name.

        Returns:
            A string with your node name.
        '''
        return self.name

    def disconnect(self):
        '''
        Disconnect from the server.

        Returns:
            None
        '''
        self._send_req(self.REQ_TYPE_DISCONNECT, None)
        self.socket.close()

    def _wait_for_connection(self, timeout=5):
        end_time = time.time() + timeout
        while time.time() < end_time:
            self.process_recv()
            peers = self.get_peers()
            if len(peers) > 0:
                return True
            time.sleep(0.1)
        return False

    def _get_peer_addr(self, name):
        if name in self.peers:
            return self.peers[name]

        if name == 'ALL':
            return self.ALL_CLIENTS

        return None

    def _send_auth(self, name, group):
        data = {
            'name': name,
            'group': group
        }
        self._send_frame(self.SERVER_ADDR, self.FRAME_TYPE_AUTH, data)

    def _send_data_frame(self, dest, data):
        self._send_frame(dest, self.FRAME_TYPE_DATA, data)

    def _send_heartbeat_frame(self):
        now = time.time()
        if now > self.heartBeatTime + 1:
            self.heartBeatTime = now
            self._send_frame(self.SERVER_ADDR, self.FRAME_TYPE_HEART, None)

    def _send_req(self, req_type, data):
        data = {
            'type': req_type,
            'data': data
        }
        self._send_frame(self.SERVER_ADDR, self.FRAME_TYPE_REQ, data)

    def _send_frame(self, dest, frame_type, data, meta=None):
        e_frame = self._encode_frame({
            'dest': dest,
            'type': frame_type,
            'data': data,
            'meta': meta
        })
        self._send_bytes(e_frame)

    def _send_bytes(self, data):
        self.outBuf += data

    def _process_inbuf(self):
        frame_bytes, self.inBuf = self._get_frame(self.inBuf)
        if frame_bytes == None:
            return

        self._process_frame(frame_bytes)
        if len(self.inBuf) > 0:
            self._process_inbuf()

    def _process_frame(self, frame):
        d_frame = self._decode_frame(frame)

        if d_frame['type'] == self.FRAME_TYPE_DATA:
            self._process_dataframe(d_frame)

        elif d_frame['type'] == self.FRAME_TYPE_PEERS:
            self._process_peersframe(d_frame)

        elif d_frame['type'] == self.FRAME_TYPE_SYSM:
            self._process_sysmframe(d_frame)

    def _get_name_from_addr(self, addr):
        for name in self.peers:
            if self.peers[name] == addr:
                return name
        return None

    def _process_dataframe(self, d_frame):
        sender_name = self._get_name_from_addr(d_frame['sender'])

        messages = self._loads(d_frame['data'])

        for message in messages:
            title = message['title']
            content = message['content']
            queue = message['queue']

            if sender_name not in self.in_data:
                self.in_data[sender_name] = {}
            if title not in self.in_data[sender_name]:
                self.in_data[sender_name][title] = []

            if queue:
                self.in_data[sender_name][title].append(content)
            else:
                self.in_data[sender_name][title] = [content]

    def _process_peersframe(self, d_frame):
        peers = self._loads(d_frame['data'])

        self.peers = {}
        for peer in peers:
            self.peers[peer['name']] = peer['addr'].to_bytes(1, 'big')

        self.my_addr = self.peers[self.name]

    def _process_sysmframe(self, d_frame):
        msg = self._loads(d_frame['data'])

        if msg['type'] == self.SYSM_TYPE_NAME:
            self._process_sysm_name(msg)

    def _process_sysm_name(self, msg):
        self.name = msg['data']

#
# Server
#


class NetServer(Net):
    '''
    The NetServer object is used to setup a nethelper server. You should
    not use this directly. Instead, run the nethelper file as a script
    to start the server.

    Args:
        host: A string specifying the interface address to bind to.
        port: An integer specifying the port to bind to.

    Returns:
        A NetServer object.
    '''
    IN_BUFFER_LIMIT = 102400
    OUT_BUFFER_LIMIT = 102400

    VERBOSITY_WARNING = 1
    VERBOSITY_INFO = 2

    _RANDOM_NAMES = ['Ant', 'Bat', 'Bear', 'Beaver', 'Bee', 'Bird', 'Bison', 'Boar', 'Buffalo', 'Camel', 'Cat', 'Cheetah', 'Chicken', 'Cobra', 'Cow', 'Crab', 'Crane', 'Crow', 'Deer', 'Dingo', 'Dog', 'Dolphin', 'Dove', 'Duck', 'Eagle', 'Elephant', 'Ferret', 'Fish', 'Fly', 'Fox', 'Frog', 'Gecko', 'Goat', 'Goldfish', 'Hamster', 'Hawk', 'Hippo',
                     'Horse', 'Hyena', 'Kangaroo', 'Kitten', 'Lion', 'Lizard', 'Lobster', 'Monkey', 'Moose', 'Mouse', 'Octopus', 'Otter', 'Owl', 'Ox', 'Panda', 'Parrot', 'Peacock', 'Pig', 'Pigeon', 'Puppy', 'Python', 'Raccoon', 'Rat', 'Raven', 'Scorpion', 'Seal', 'Shark', 'Sheep', 'Snail', 'Snake', 'Spider', 'Squirrel', 'Tiger', 'Turkey', 'Whale', 'Wolf', 'Zebra']
    random.shuffle(_RANDOM_NAMES)

    def __init__(self, host=None, port=None):
        self.clients = []
        self.groups = []
        self.sel = selectors.DefaultSelector()
        self.verbosity = self.VERBOSITY_INFO
        self.my_addr = self.SERVER_ADDR

        if host and port:
            self.listen(host, port)

    def print(self, level, *arg):
        if self.verbosity >= level:
            print(*arg)

    def listen(self, host, port=None):
        if port == None:
            port = self.DEFAULT_PORT

        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind((host, port))
        self.lsock.setblocking(False)
        self.lsock.listen()
        self.sel.register(self.lsock, selectors.EVENT_READ, data=None)

    def loop(self, timeout=0):
        events = self.sel.select(timeout=timeout)
        accepted = []
        for key, mask in events:
            if key.data is None:
                a = self._accept_connection(key.fileobj)
                accepted.append(a)
            else:
                self._service_connection(key, mask)
        return accepted

    def disconnect_if_timeout(self):
        now = time.time()
        disconnected = []
        for client in self.clients:
            if client['watchDog'] < now - 5:
                disconnected.append(client['ip'])
                self.disconnect(client)
        return disconnected

    def disconnect(self, client):
        try:
            self.sel.unregister(client['sock'])
            client['sock'].close()
        except:
            pass
        if client in self.clients:
            self.clients.remove(client)
        # Inform all in group that one of peers is disconnected
        self._send_peers_frame(client['group'])

    def _accept_connection(self, sock):
        conn, ip = sock.accept()  # Should be ready to read
        conn.setblocking(False)
        client = {
            'ip': ip,
            'name': '',
            'group': '',
            'addr': self.UNKNOWN_ADDR,
            'inb': b'',
            'outb': b'',
            'sock': conn,
            'watchDog': time.time()
        }
        events = selectors.EVENT_READ
        self.sel.register(conn, events, data=client)
        self.clients.append(client)
        return ip

    def _service_connection(self, key, mask):
        if mask & selectors.EVENT_READ:
            self._service_read(key)
            self._write_all()

    def _service_read(self, key):
        sock = key.fileobj
        client = key.data
        try:
            recv_data = sock.recv(1024)  # Should be ready to read
            if recv_data:
                client['inb'] += recv_data
                buf_size = len(client['inb'])
                if buf_size > self.IN_BUFFER_LIMIT:
                    self.print(self.VERBOSITY_WARNING,
                               'IN_BUFFER_LIMIT exceeded. Closing', client['ip'])
                    self.disconnect(client)
                    return
                self._process_buf(client)
            else:
                self.print(self.VERBOSITY_INFO,
                           'Client disconnected. Closing', client['ip'])
                self.disconnect(client)

        except (ConnectionError, OSError):
            self.print(self.VERBOSITY_WARNING,
                       'Read connection error. Closing', client['ip'])
            self.disconnect(client)
        except TimeoutError:
            pass

    def _write_all(self):
        for client in self.clients:
            if client['outb']:
                sock = client['sock']
                try:
                    sent = sock.send(client['outb'])  # Should be ready to write
                    client['outb'] = client['outb'][sent:]
                except (ConnectionError, OSError):
                    self.print(self.VERBOSITY_WARNING,
                               'Write connection error. Closing', client['ip'])
                    self.disconnect(client)

    def _get_client_by_addr(self, addr, group):
        for client in self.clients:
            if client['addr'] == addr and client['group'] == group:
                return client
        return None

    def _get_client_by_name(self, name, group):
        return [client for client in self.clients if client['group'] == group and client['name'] == name]

    def _get_clients_by_group(self, group):
        return [client for client in self.clients if client['group'] == group]

    def _get_free_addr(self, group):
        for addr in range(1, 255):
            b_addr = addr.to_bytes(1, 'big')
            if self._get_client_by_addr(b_addr, group) == None:
                return b_addr
        return None

    def _get_random_name(self, group):
        used_names = []
        for client in self._get_clients_by_group(group):
            used_names.append(client['name'])

        for name in self._RANDOM_NAMES:
            if name not in used_names:
                return name

        for a in range(1, 255):
            for name in self._RANDOM_NAMES:
                name += str(a)
                if name not in used_names:
                    return name

        return None

    def _get_peers_list(self, group):
        data = []
        clients = self._get_clients_by_group(group)
        for client in clients:
            data.append({
                'name': client['name'],
                'addr': int.from_bytes(client['addr'], 'big')
            })

        return data

    def _send_bytes(self, client, data):
        client['outb'] += data

    def _process_buf(self, client):
        frame_bytes, client['inb'] = self._get_frame(client['inb'])
        if frame_bytes == None:
            return

        self._process_frame(frame_bytes, client)
        self._process_buf(client)

    def _process_frame(self, frame_bytes, client):
        d_frame = self._decode_frame(frame_bytes)

        if d_frame['type'] == self.FRAME_TYPE_AUTH:
            self._process_authframe(client, d_frame)
            return

        # Only authenticated clients may proceed
        if client['group'] == '':
            return

        # Reject forged sender addr
        if client['addr'] != d_frame['sender']:
            self.print(self.VERBOSITY_WARNING, 'Forged sender addr.', client['ip'])
            return

        # Update watchdog
        client['watchDog'] = time.time()

        if d_frame['type'] == self.FRAME_TYPE_DATA:
            self._process_dataframe(client, d_frame, frame_bytes)

    def _process_authframe(self, client, d_frame):
        auth_info = self._loads(d_frame['data'])
        name = auth_info['name']
        group = auth_info['group']

        if group in self.groups:
            if name == '':
                name = self._get_random_name(group)
                if name == None:
                    self.print(self.VERBOSITY_WARNING,
                               'Unable to find unused name. Closing', client['ip'])
                    self.disconnect(client)
                    return
                self._send_sysm_name_frame(client, name)
            elif self._get_client_by_name(name, group):
                self.print(self.VERBOSITY_WARNING,
                           'Repeated name. Closing', client['ip'])
                self.disconnect(client)
                return

            self.print(self.VERBOSITY_INFO, 'Auth passed', name, group)
            addr = self._get_free_addr(group)
            if addr == None:
                self.print(self.VERBOSITY_WARNING,
                           'No free addresses. Closing', client['ip'])
                self.disconnect(client)
                return
            client['name'] = name
            client['group'] = group
            client['addr'] = addr
            self._send_peers_frame(group)
        else:
            self.print(self.VERBOSITY_WARNING, 'Auth failed. Closing', client['ip'])
            self.disconnect(client)

    def _process_dataframe(self, client, d_frame, frame):
        if d_frame['dest'] == self.ALL_CLIENTS:
            clients = self._get_clients_by_group(client['group'])
            for dest_client in clients:
                if dest_client['addr'] != d_frame['sender']:
                    self._send_bytes(dest_client, frame)
        else:
            dest_client = self._get_client_by_addr(d_frame['dest'], client['group'])
            if dest_client:
                self._send_bytes(dest_client, frame)

    def _process_reqframe(self, client, d_frame):
        req = self._loads(d_frame['data'])

        if req['type'] == self.REQ_TYPE_DISCONNECT:
            self.disconnect(client)
        elif req['type'] == self.REQ_TYPE_PEERS:
            e_frame = self._encode_frame({
                'dest': client['addr'],
                'type': self.FRAME_TYPE_PEERS,
                'data': self._get_peers_list(group)
            })
            self._send_bytes(client, e_frame)

    def _send_peers_frame(self, group):
        e_frame = self._encode_frame({
            'dest': self.ALL_CLIENTS,
            'type': self.FRAME_TYPE_PEERS,
            'data': self._get_peers_list(group)
        })

        for client in self._get_clients_by_group(group):
            self._send_bytes(client, e_frame)

    def _send_sysm_name_frame(self, client, name):
        e_frame = self._encode_frame({
            'dest': client['addr'],
            'type': self.FRAME_TYPE_SYSM,
            'data': {
                'type': self.SYSM_TYPE_NAME,
                'msg': None,
                'data': name
            }
        })

        self._send_bytes(client, e_frame)


# Run server
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--interface',
                        help='interface address to bind to (default is all interfaces)')
    parser.add_argument(
        '-p', '--port', help='port to bind to (default is ' + str(Net.DEFAULT_PORT) + ')')
    parser.add_argument(
        '-n', '--names', help='file containing random names. If unspecified, a built-in list of names will be used.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-f', '--file', help='File providing list of group. Each group should be on its own line. Lines starting with # are ignored. Leading and trailing whitepspaces are ignored.')
    group.add_argument('-g', '--groups', nargs='+',
                       help='List of group separated by a space.')
    args = parser.parse_args()

    print('Starting Server')

    if args.interface:
        host = args.interface
        print('  Interface:', args.interface)
    else:
        host = None
        print('  Interface: ALL')

    if args.port:
        port = args.port
    else:
        port = Net.DEFAULT_PORT
    print('  Port:     ', port)

    groups = []
    if args.file:
        with open(args.file, 'r') as file:
            for line in file.readlines():
                line = line.strip()
                if len(line) > 0 and line[0] != '#':
                    groups.append(line)
    else:
        groups = args.groups

    groups_string = ''
    for group in groups:
        groups_string += group + ', '
    print('  Groups:   ', groups_string[:-2])

    net_server = NetServer(host=host, port=port)
    net_server.listen('')
    net_server.groups = args.groups

    print('Server listening')

    if args.names:
        net_server._RANDOM_NAMES = []
        with open(args.file, 'r') as file:
            for line in file.readlines():
                line = line.strip()
                if len(line) > 0 and line[0] != '#':
                    net_server._RANDOM_NAMES.append(line)
        random.shuffle(net_server._RANDOM_NAMES)
        print('  Read from file: ' + str(len(net_server._RANDOM_NAMES)) + ' names')

    display_timeout = time.time() + 5
    while True:
        accepted = net_server.loop(1)

        now = time.time()
        if now > display_timeout:
            for group in net_server.groups:
                peers = net_server._get_clients_by_group(group)
                if len(peers) > 0:
                    print('===== ' + group + ' =====')
                    for peer in peers:
                        print(peer['name'], '( in:', len(peer['inb']),
                              'out:', len(peer['outb']), ')')
            display_timeout = now + 5

        for a in accepted:
            print('Connected', a)
        disconnected = net_server.disconnect_if_timeout()
        for d in disconnected:
            print('Time out. Closing', d)
