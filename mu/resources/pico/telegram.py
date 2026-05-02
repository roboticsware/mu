# This project contains code with dual licensing:
#
# The original micropython-telegram-bot code, created by Salvatore Sanfilippo (@antirez),
# is released under the BSD 2-clause license
# Copyright (C) 2024 Salvatore Sanfilippo <antirez@gmail.com>
# All Rights Reserved
#
# All additional code, extensions, examples, and customizations beyond the original
# micropython-telegram-bot implementation are licensed under the
# GNU Affero General Public License v3.0 (AGPL-3.0)
# Made by Emilio Destratis - destone28 <emilio.destratis@gmail.com>
#
# See the LICENSE file for more information

import network, socket, ssl, time, uasyncio as asyncio, json, os, gc

class TelegramBot:
    def __init__(self,token,callback):
        self.token = token
        self.callback = callback
        self.rbuf = bytearray(4096)
        self.rbuf_mv = memoryview(self.rbuf)
        self.rbuf_used = 0
        self.active = True # So we can stop the task with .stop()
        self.debug = False
        self.missed_write = None # Failed write payload. This is useful
                                 # in order to retransfer after reconnection.

        # Array of outgoing messages. Each entry is a hash with
        # chat_id and text fields.
        self.outgoing = []
        self.pending = False # Pending HTTP request, waiting for reply.
        self.reconnect = True # We need to reconnect the socket, either for
                              # the first time or after errors.
        self.offset = 0     # Next message ID offset.
        self.watchdog_timeout_ms = 60000 # 60 seconds max idle time.
        self.max_image_size = 50000  # Limit the image size (about 50KB)

    # Stop the task handling the bot. This should be called before
    # destroying the object, in order to also terminate the task.
    def stop(self):
        self.active = False

    # Main telegram bot loop.
    # Should be executed asynchronously, like with:
    # asyncio.create_task(bot.run())
    async def run(self):
        print("[telegram] Bot task started")
        while self.active:
            if self.reconnect:
                if self.debug: print("[telegram] Reconnecting socket.")
                # Reconnection (or first connection)
                try:
                    addr = socket.getaddrinfo("api.telegram.org", 443, socket.AF_INET)
                    addr = addr[0][-1]
                    self.socket = socket.socket(socket.AF_INET)
                    self.socket.connect(addr)
                    self.socket.setblocking(False)
                    self.ssl = ssl.wrap_socket(self.socket)
                    self.reconnect = False
                    self.pending = False
                except Exception as e:
                    print(f"[telegram] Reconnection error: {e}")
                    self.reconnect = True
                    await asyncio.sleep(5)  # Wait before retrying

            # Add here for debugging
            if self.debug and not self.pending:
                print("[telegram] Checking for updates...")

            self.send_api_requests()
            self.read_api_response()

            # Add here for debugging
            if self.debug and self.pending:
                print(f"[telegram] Waiting for response, pending since {time.ticks_diff(time.ticks_ms(),self.pending_since)}ms")

            # Watchdog: if the connection is idle for too long
            # time, force a reconnection.
            if self.pending and time.ticks_diff(time.ticks_ms(),self.pending_since) > self.watchdog_timeout_ms:
                self.reconnect = True
                print("[telegram] *** SOCKET WATCHDOG EXPIRED ***")

            # If there are outgoing messages pending, wait less
            # to do I/O again.
            sleep_time = 0.1 if len(self.outgoing) > 0 else 1.0
            await asyncio.sleep(sleep_time)

    # Send HTTP requests to the server. If there are no special requests
    # to handle (like sendMessage) we just ask for updates with getUpdates.
    def send_api_requests(self):
        if self.pending: return # Request already in progress.
        request = None

        # Re-issue a pending write that failed for OS error
        # after a reconnection.
        if self.missed_write != None:
            request = self.missed_write
            self.missed_write = None

        # Issue sendMessage requests if we have pending
        # messages to deliver.
        elif len(self.outgoing) > 0:
            oldest = self.outgoing.pop(0)  # Use FIFO order for messages
            request = self.build_post_request("sendMessage", oldest)

        # Issue a new getUpdates request if there is not
        # some request still pending.
        else:
            # Limit the fetch to a single message since we are using
            # a fixed 4k buffer. Very large incoming messages will break
            # the reading loop: that's a trade off.
            request = "GET /bot"+self.token+"/getUpdates?offset="+str(self.offset)+"&timeout=0&allowed_udpates=message&limit=1 HTTP/1.1\r\nHost:api.telegram.org\r\n\r\n"

        # Write the request to the SSL socket.
        if request != None:
            if self.debug: print("[telegram] Writing payload:", request[:100] + "..." if len(request) > 100 else request)
            try:
                if isinstance(request, str):
                    self.ssl.write(request)
                else:
                    # If it's bytes, write directly
                    self.ssl.write(request)
                self.pending = True
                self.pending_since = time.ticks_ms()
            except Exception as e:
                print(f"[telegram] Error writing request: {e}")
                self.reconnect = True
                self.missed_write = request

    # Try to read the reply from the Telegram server. Process it
    # and if needed invoke the callback registered by the user for
    # incoming messages.
    def read_api_response(self):
        try:
            # Don't use await to read from the SSL socket (it's not
            # supported). We put the socket in non blocking mode
            # anyway. It will return None if there is no data to read.
            nbytes = self.ssl.readinto(self.rbuf_mv[self.rbuf_used:], len(self.rbuf)-self.rbuf_used)
            if self.debug: print("bytes from SSL socket:", nbytes)
        except Exception as e:
            print(f"[telegram] Socket read error: {e}")
            self.reconnect = True
            return

        if nbytes != None:
            if nbytes == 0:
                self.reconnect = True
                return
            else:
                self.rbuf_used += nbytes
                if self.debug and self.rbuf_used < 100:
                    print(self.rbuf[:self.rbuf_used])

        # Check if we got a well-formed JSON message.
        self.process_api_response()

    # Check if there is a well-formed JSON reply in the reply buffer:
    # if so, parses it, marks the current request as no longer "pending"
    # and resets the buffer. If the JSON reply is an incoming message, the
    # user callback is invoked.
    def process_api_response(self):
        if self.rbuf_used > 0:
            if self.debug: print(f"[telegram] Processing response buffer ({self.rbuf_used} bytes)")
            # Discard the HTTP request header by looking for the
            # start of the json message.
            start_idx = self.rbuf.find(b"{")
            if start_idx != -1:
                # It is possible that we read a non complete reply
                # from the socket. In such case the JSON message
                # will be broken and will produce a ValueError.
                try:
                    mybuf = self.decode_surrogate_pairs(self.rbuf[start_idx:self.rbuf_used])
                    res = json.loads(mybuf)
                    if res != False:
                        if self.debug: print(f"[telegram] Valid JSON response: {res}")
                except ValueError:
                    res = False
                if res != False:
                    self.pending = False
                    if 'result' not in res:
                        # Probably an error response from a sendPhoto or sendMessage request
                        if self.debug: print(f"[telegram] Error response: {res}")
                    elif len(res['result']) == 0:
                        # Empty result set. Try again.
                        if self.debug: print("No more messages.")
                    elif not isinstance(res['result'], list):
                        # This is the reply to SendMessage or other
                        # non getUpdates related API calls? Discard it.
                        if self.debug: print("Got reply from sendMessage/sendPhoto")
                    else:
                        # Update the last message ID we get so we
                        # will get only next ones.
                        offset = res['result'][0]['update_id']
                        offset += 1
                        self.offset = offset
                        if self.debug: print("New offset:", offset)

                        # Process the received message.
                        entry = res['result'][0]
                        if "message" in entry:
                            msg = entry['message']
                        elif "channel_post" in entry:
                            msg = entry['channel_post']

                        # Fill the fields depending on the message
                        msg_type = None
                        chat_name = None
                        sender_name = None
                        chat_id = None
                        text = None

                        try: msg_type = msg['chat']['type']
                        except: pass
                        try: chat_name = msg['chat']['title']
                        except: pass
                        try: sender_name = msg['from']['username']
                        except: pass
                        try: chat_id = msg['chat']['id']
                        except: pass
                        try: text = msg['text']
                        except: pass

                        # We don't care about join messages and other stuff.
                        # We report just messages with some text content.
                        if text != None:
                            self.callback(self, msg_type, chat_name, sender_name, chat_id, text, entry)
                            if self.debug: print(f"[telegram] Calling callback with text: {text}")
                    self.rbuf_used = 0

    # MicroPython seems to lack the urlencode module. We need very
    # little to kinda make it work.
    def quote(self, string):
        return ''.join(['%{:02X}'.format(c) if c < 33 or c > 126 or c in (37, 38, 43, 58, 61) else chr(c) for c in str(string).encode('utf-8')])

    # Turn the GET/POST parameters in the 'fields' hash into a string
    # in url encoded form a=1&b=2&... quoting just the value (the key
    # of the hash is assumed to be already url encoded or just a plain
    # string without special chars).
    def urlencode(self, fields):
        return "&".join([str(key)+"="+self.quote(value) for key, value in fields.items()])

    # Create a POST request with url-encoded parameters in the body.
    # Parameters are passed as a hash in 'fields'.
    def build_post_request(self, cmd, fields):
        params = self.urlencode(fields)
        headers = f"POST /bot{self.token}/{cmd} HTTP/1.1\r\nHost:api.telegram.org\r\nContent-Type:application/x-www-form-urlencoded\r\nContent-Length:{len(params)}\r\n\r\n"
        return headers+params

    # MicroPython JSON library does not handle surrogate UTF-16 pairs
    # generated by the Telegram API. We need to do it manually by scanning
    # the input bytearray and converting the surrogates to UTF-8.
    def decode_surrogate_pairs(self, ba):
        result = bytearray()
        i = 0
        while i < len(ba):
            if ba[i:i+2] == b'\\u' and i + 12 <= len(ba):
                if ba[i+2:i+4] in [b'd8', b'd9', b'da', b'db'] and ba[i+6:i+8] == b'\\u' and ba[i+8:i+10] in [b'dc', b'dd', b'de', b'df']:
                    # We found a surrogate pairs. Convert.
                    high = int(ba[i+2:i+6].decode(), 16)
                    low = int(ba[i+8:i+12].decode(), 16)
                    code_point = 0x10000 + (high - 0xD800) * 0x400 + (low - 0xDC00)
                    result.extend(chr(code_point).encode('utf-8'))
                    i += 12
                else:
                    result.append(ba[i])
                    i += 1
            else:
                result.append(ba[i])
                i += 1
        return result

    # Send a message via Telegram, to the specified chat_id and containing
    # the specified text. This function will just queue the item. The
    # actual sending will be performed in the main boot loop.
    #
    # If 'glue' is True, the new text will be glued to the old pending
    # message up to 2k, in order to reduce the API back-and-forth.
    def send(self, chat_id, text, glue=False):
        if glue and len(self.outgoing) > 0 and \
           len(self.outgoing[0]["text"])+len(text)+1 < 2048:
            self.outgoing[0]["text"] += "\n"
            self.outgoing[0]["text"] += text
            return
        self.outgoing.append({"chat_id": chat_id, "text": text})

    # Fully simplified implementation to send a photo
    def send_photo(self, chat_id, photo_path, caption=None):
        try:
            # Check if file exists and get its size
            try:
                stats = os.stat(photo_path)
                file_size = stats[6]  # Size in bytes

                if file_size > self.max_image_size:
                    # File is too large
                    self.send(chat_id, f"📷 Photo taken! Size {file_size/1024:.1f}KB (too large for direct sending)")
                    return False
            except OSError:
                self.send(chat_id, f"⚠️ Error: unable to find the file '{photo_path}'")
                return False

            # Force garbage collection before starting
            gc.collect()

            print(f"[telegram] Sending photo {photo_path} ({file_size} bytes) to {chat_id}")

            # Read the photo into memory
            try:
                with open(photo_path, 'rb') as f:
                    photo_data = f.read()
            except Exception as e:
                print(f"[telegram] Error reading photo file: {e}")
                self.send(chat_id, f"⚠️ File read error: {e}")
                return False

            # Send the photo using a normal POST request with URL param "chat_id"
            # and the "document" field containing the file
            try:
                # Create a new dedicated connection
                addr = socket.getaddrinfo("api.telegram.org", 443, socket.AF_INET)
                addr = addr[0][-1]
                sock = socket.socket(socket.AF_INET)
                sock.connect(addr)
                sock.setblocking(True)  # Blocking mode
                ssl_sock = ssl.wrap_socket(sock)

                # Simple static boundary
                boundary = "----WebKitFormBoundaryNiclaVision"

                # Form content
                form_data = bytearray()

                # chat_id field
                form_data.extend(f"--{boundary}\r\n".encode())
                form_data.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())

                # caption field if present
                if caption:
                    form_data.extend(f"--{boundary}\r\n".encode())
                    form_data.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())

                # "document" field with the file
                form_data.extend(f"--{boundary}\r\n".encode())
                form_data.extend(f'Content-Disposition: form-data; name="document"; filename="photo.jpg"\r\n'.encode())
                form_data.extend(f'Content-Type: image/jpeg\r\n\r\n'.encode())

                # Add the file content
                end_boundary = f"\r\n--{boundary}--\r\n".encode()

                # Calculate the total length
                total_length = len(form_data) + len(photo_data) + len(end_boundary)

                # Create the HTTP header
                header = f"POST /bot{self.token}/sendDocument HTTP/1.1\r\n"
                header += "Host: api.telegram.org\r\n"
                header += f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
                header += f"Content-Length: {total_length}\r\n"
                header += "Connection: close\r\n\r\n"

                # Send the header
                ssl_sock.write(header.encode())

                # Send the first part of the form
                ssl_sock.write(form_data)

                # Send the file content
                ssl_sock.write(photo_data)

                # Send the final part
                ssl_sock.write(end_boundary)

                # Read the response
                response = bytearray(1024)
                bytes_read = ssl_sock.readinto(response)
                response_text = response[:bytes_read].decode('utf-8', 'ignore')

                # Close the socket
                ssl_sock.close()
                sock.close()

                # Check if the response is positive
                if "HTTP/1.1 200" in response_text:
                    print("[telegram] Photo sent successfully!")
                    return True
                else:
                    # Look for more error information in the response
                    error_info = response_text.split("\r\n\r\n")[-1] if "\r\n\r\n" in response_text else response_text
                    print(f"[telegram] Error response: {error_info[:200]}")
                    self.send(chat_id, f"⚠️ Error sending photo. Please try again later.")
                    return False

            except Exception as e:
                print(f"[telegram] Error in send_photo transaction: {e}")
                self.send(chat_id, f"⚠️ Sending error: {e}")
                return False

        except Exception as e:
            print(f"[telegram] Error in send_photo: {e}")
            self.send(chat_id, f"⚠️ Generic error: {e}")
            return False

    def send_video(self, chat_id, video_path, caption=None):
        """
        Send a video via Telegram using a chunked approach to save memory

        Args:
            chat_id: Chat ID
            video_path: Video file path
            caption: Optional description

        Returns:
            bool: True if the video was sent, False otherwise
        """
        try:
            # Check if the file exists and get its size
            try:
                stats = os.stat(video_path)
                file_size = stats[6]  # Size in bytes

                # Use a hardcoded value
                max_video_size = 10000000  # 10MB (reasonable threshold for Telegram)

                if file_size > max_video_size:
                    # File is too large
                    self.send(chat_id, f"🎥 Video recorded! Size {file_size/1024/1024:.1f}MB (too large for direct sending)")
                    return False
            except OSError:
                self.send(chat_id, f"⚠️ Error: unable to find the file '{video_path}'")
                return False

            # Force garbage collection before starting
            gc.collect()

            print(f"[telegram] Sending video {video_path} ({file_size} bytes) to {chat_id}")

            # Send the video using a normal POST request with URL param "chat_id"
            # and the "document" field containing the file
            try:
                # Create a new dedicated connection
                addr = socket.getaddrinfo("api.telegram.org", 443, socket.AF_INET)
                addr = addr[0][-1]
                sock = socket.socket(socket.AF_INET)
                sock.connect(addr)
                sock.setblocking(True)  # Blocking mode
                ssl_sock = ssl.wrap_socket(sock)

                # Simple static boundary
                boundary = "----WebKitFormBoundaryNiclaVision"

                # Form content
                form_data = bytearray()

                # chat_id field
                form_data.extend(f"--{boundary}\r\n".encode())
                form_data.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())

                # caption field if present
                if caption:
                    form_data.extend(f"--{boundary}\r\n".encode())
                    form_data.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())

                # "document" field with the file
                form_data.extend(f"--{boundary}\r\n".encode())
                form_data.extend(f'Content-Disposition: form-data; name="document"; filename="video.mjpeg"\r\n'.encode())
                form_data.extend(f'Content-Type: video/mjpeg\r\n\r\n'.encode())

                # End of the form (to be added after the file content)
                end_boundary = f"\r\n--{boundary}--\r\n".encode()

                # Calculate the total length
                total_length = len(form_data) + file_size + len(end_boundary)

                # Create the HTTP header
                header = f"POST /bot{self.token}/sendDocument HTTP/1.1\r\n"
                header += "Host: api.telegram.org\r\n"
                header += f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
                header += f"Content-Length: {total_length}\r\n"
                header += "Connection: close\r\n\r\n"

                # Send the header
                ssl_sock.write(header.encode())

                # Send the first part of the form
                ssl_sock.write(form_data)

                # Read and send the file in chunks to save memory
                chunk_size = 4096  # chunk size (4KB)
                sent_bytes = 0

                try:
                    with open(video_path, 'rb') as f:
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            ssl_sock.write(chunk)
                            sent_bytes += len(chunk)
                            # Feedback on stdout every 20KB
                            if sent_bytes % 20480 == 0:
                                print(f"[telegram] Sent {sent_bytes/1024:.1f}KB/{file_size/1024:.1f}KB")
                            # Free memory
                            del chunk
                            gc.collect()
                except Exception as e:
                    print(f"[telegram] Error during video data sending: {e}")
                    ssl_sock.close()
                    sock.close()
                    self.send(chat_id, f"⚠️ Error during video sending: {e}")
                    return False

                # Send the final part
                ssl_sock.write(end_boundary)

                # Read the response
                response = bytearray(1024)
                bytes_read = ssl_sock.readinto(response)
                response_text = response[:bytes_read].decode('utf-8', 'ignore')

                # Close the socket
                ssl_sock.close()
                sock.close()

                # Check if the response is positive
                if "HTTP/1.1 200" in response_text:
                    print("[telegram] Video sent successfully!")
                    return True
                else:
                    # Look for more error information in the response
                    error_info = response_text.split("\r\n\r\n")[-1] if "\r\n\r\n" in response_text else response_text
                    print(f"[telegram] Error response: {error_info[:200]}")
                    self.send(chat_id, f"⚠️ Error sending video. Please try again later.")
                    return False

            except Exception as e:
                print(f"[telegram] Error in send_video transaction: {e}")
                self.send(chat_id, f"⚠️ Sending video error: {e}")
                return False

        except Exception as e:
            print(f"[telegram] Error in send_video: {e}")
            self.send(chat_id, f"⚠️ Generic video sending error: {e}")
            return False

    # This is just a utility method that can be used in order to wait
    # for the WiFi network to be connected.
    def connect_wifi(self, ssid, password, timeout=30):
        self.sta_if = network.WLAN(network.STA_IF)
        self.sta_if.active(True)
        self.sta_if.connect(ssid, password)
        seconds = 0
        while not self.sta_if.isconnected():
            time.sleep(1)
            seconds += 1
            if seconds == timeout:
                raise Exception("Timed out connecting to WiFi network")
            pass
        print("[WiFi] Connected")
