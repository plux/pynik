from __future__ import with_statement

import sys
import socket
import re

class IRCClient:
	def __init__(self):
		self.connected = False
		self.active_session = False
		self.temp_nick_list_channel = None
		self.temp_nick_list = None
		self.nick_lists = {}
		self.recv_buf = ''
		self.callbacks = {}

		self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		self.irc_message_pattern = re.compile('^(:([^  ]+))?[   ]*([^  ]+)[  ]+:?([^  ]*)[   ]*:?(.*)$')
		self.message_handlers = {
			'JOIN': self.on_join,
			'KICK': self.on_kick,
			'NICK': self.on_nick,
			'PART': self.on_part,
			'QUIT': self.on_quit,
			'PING': self.on_ping,
			'PRIVMSG': self.on_privmsg,
			'NOTICE': self.on_notice,
			'ERROR': self.on_error,
			'353': self.on_begin_nick_list,
			'366': self.on_end_nick_list,
		}

	def connect(self, address, port):
		self.active_session = False
		self.ping_count = 0
		self.connected = self.s.connect_ex((address, port)) == 0

		if self.connected:
			self.s.setblocking(False)

		return self.connected

	def send(self, line):
		print line
		return self.s.send(line + "\r\n")

	def is_connected(self):
		return self.connected

	def tell(self, target, string):
		split = len(string) - 1

		if split >= 400:
			split = 400
			while split > 350:
				if string[split] == ' ':
					break
				split -= 1

			a = string[0:split]
			b = string[split:]
		
			return self.tell(target, a) + self.tell(target, b)
		else:
			return self.send("PRIVMSG " + target + " :" + string)

	def join(self, channel):
		return self.send('JOIN ' + channel)

	def get_nick(self, host):
		m = re.search('^:?(\S+?)!', host)
		if m:
			return m.group(1)
		else:
			return host

	def on_begin_nick_list(self, tupels):
		m = re.search('. (.+?) :(.*)$', tupels[5])

		if m:
			channel, nicks = m.group(1, 2)

			if self.temp_nick_list_channel != channel:
				self.temp_nick_list_channel = channel
				self.temp_nick_list = []

			for m in re.findall('([^a-zA-Z\[\]{}]?)(.+?)(\s|$)', nicks):
				prefix, nick = m[0:2]

				self.temp_nick_list.append(nick)
			
	def on_end_nick_list(self, tupels):
		self.nick_lists[self.temp_nick_list_channel] = self.temp_nick_list
		self.temp_nick_list_channel = None
		self.temp_nick_list = None

	def on_join(self, tupels):
		source, channel = [tupels[1], tupels[4]]

		if "on_join" in self.callbacks:
			self.callbacks["on_join"](source, channel)

	def on_kick(self, tupels):
		source, channel = [tupels[1], tupels[4]]
		target_nick = None

		m = re.search('^([^ ]+)', tupels[5])
		if m:
			target_nick = m.group(1)

		if "on_kick" in self.callbacks:
			self.callbacks["on_kick"](source, channel, target_nick)

		if target_nick:
			for nick_list in self.nick_lists.values():
				if target_nick in nick_list:
					nick_list.remove(target_nick)

	def on_nick(self, tupels):
		source, new_nick = [tupels[1], tupels[4]]

		if "on_nick_change" in self.callbacks:
			self.callbacks["on_nick_change"](source, new_nick)

		source_nick = self.get_nick(source)

		for nick_list in self.nick_lists.values():
			if source_nick in nick_list:
				nick_list.remove(source_nick)
				nick_list.append(new_nick)

	def on_part(self, tupels):
		source, channel, reason = [tupels[1], tupels[4], tupels[5]]

		if "on_part" in self.callbacks:
			self.callbacks["on_part"](source, channel, reason)

		source_nick = self.get_nick(source)

		for nick_list in self.nick_lists.values():
			if source_nick in nick_list:
				nick_list.remove(source_nick)

	def on_quit(self, tupels):
		source = tupels[1]
		reason = tupels[4]

		if tupels[5]:
			reason += ' ' + tupels[5]

		source_nick = self.get_nick(source)

		if "on_quit" in self.callbacks:
			self.callbacks["on_quit"](source_nick, reason)

		for nick_list in self.nick_lists.values():
			if source_nick in nick_list:
				nick_list.remove(source_nick)

	def on_ping(self, tupels):
		self.send("PONG :" + tupels[4])

		if not self.active_session:
			self.active_session = True
			self.on_connected(tupels)

	def on_privmsg(self, tupels):
		source, target, message = tupels[2], tupels[4], tupels[5]

		if target[0] != '#':
			target = source

		if "on_privmsg" in self.callbacks:
			self.callbacks["on_privmsg"](source, target, message)

	def on_notice(self, tupels):
		source, target, message = tupels[2], tupels[4], tupels[5]

		if target[0] != '#':
			target = source

		if "on_notice" in self.callbacks:
			self.callbacks["on_notice"](source, target, message)

	def on_connected(self, tupels):
		if "on_connected" in self.callbacks:
			self.callbacks["on_connected"]()

	def on_error(self, tupels):
		print 'the irc server informs of an error: ' + tupels[5]

	def tick(self):
		try:
			retn = self.s.recv(1024)

			self.recv_buf += retn
			recv_lines = self.recv_buf.splitlines(True)
			self.recv_buf = ''
			for line in recv_lines:
				if not line.endswith("\r\n"):
					self.recv_buf = line
				else:
					line = line.rstrip("\r\n")
					m = self.irc_message_pattern.match(line)
					if m:
						if m.group(3) in self.message_handlers:
							self.message_handlers[m.group(3)](m.group(0, 1, 2, 3, 4, 5))

		except socket.error:
			pass
