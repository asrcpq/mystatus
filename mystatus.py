#!/usr/bin/env python3

import datetime
import json
import netifaces
import os
import re
import signal
import sys
from alsaaudio import Mixer, ALSAAudioError
from netaddr import IPAddress
from time import sleep

sleep_time = 5
mystatus = dict()
flush_flag = False
dirty_flag = False
dirty_up_thresh = 100_000
dirty_down_thresh = 10_000
disk_dict = dict()

def parse_line(line):
	global mixer
	line_split = line.split()
	if line_split[0] != 'volume':
		return
	if line_split[2] == 'up':
		volume = [min(100, x + 3) for x in mixer[line_split[1]].getvolume()]
		mixer[line_split[1]].setvolume(volume[0])
	elif line_split[2] == 'down':
		volume = [max(0, x - 3) for x in mixer[line_split[1]].getvolume()]
		mixer[line_split[1]].setvolume(volume[0])
	elif line_split[2] == 'toggle':
		mute = [1 - x for x in mixer[line_split[1]].getmute()]
		mixer[line_split[1]].setmute(mute[0])
	else:
		return

def try_readline():
	global fifoid
	line = ''
	while True:
		buf = os.read(fifoid, 1)
		if not buf:
			break
		else:
			if buf == b'\n':
				parse_line(line)
				line = ''
			else:
				line += buf.decode('utf-8')

def flush_volume(sig, frame):
	global flush_flag
	try_readline()
	module_volume(True)
	flush_status()
	flush_flag = True

def flush_all(sig, frame):
	global flush_flag
	try_readline()
	update_modules()
	flush_status()
	flush_flag = True

cpu_usage1 = 0
cpu_usage2 = 0
def module_cpufreq():
	global cpu_usage1, cpu_usage2
	mystatus.pop('cpufreq', None)
	try:
		with open('/proc/cpuinfo', 'r') as f:
			sum_freq=0
			sum_core=0
			for line in f:
				if "MHz" in line:
					sum_freq += float(re.search(r'[0-9]*\.[0-9]*', line).group())
					sum_core += 1
			avg_freq = int(sum_freq / sum_core)
		with open('/proc/stat', 'r') as f:
			t = [int(i) for i in f.readline().split()[1:]]
			new1 = t[0] + t[2]
			new2 = new1 + t[3]
			usage_percent = (new1 - cpu_usage1) * 100 // (new2 - cpu_usage2)
			cpu_usage1 = new1
			cpu_usage2 = new2
		result = {"full_text": "C:" + str(avg_freq) + " " + str(usage_percent) + "%"}
		mystatus['cpufreq'] = result
	except FileNotFoundError:
		pass

def module_cputemp():
	mystatus.pop('cputemp', None)
	try:
		with open('/sys/devices/LNXSYSTM:00/LNXCPU:00/thermal_cooling/subsystem/thermal_zone0/temp', 'r') as f:
			line = f.readline()
			temp = int(line) // 1000
			result = {"full_text": "T:" + str(temp)}
			if temp > 85:
				result['color'] = '#FF0000'
			mystatus['cputemp'] = result
	except FileNotFoundError:
		pass

def module_memory():
	global dirty_flag
	mystatus.pop('memory', None)
	try:
		with open('/proc/meminfo', 'r') as f:
			meminfo = f.read()
		total = int(re.search(r'^MemTotal:\s+(\d+)', meminfo, flags = re.M).groups()[0])
		free = int(re.search(r'^MemFree:\s+(\d+)', meminfo, flags = re.M).groups()[0])
		avail = int(re.search(r'^MemAvailable:\s+(\d+)', meminfo, flags = re.M).groups()[0])
		dirty = int(re.search(r'^Dirty:\s+(\d+)', meminfo, flags = re.M).groups()[0])
		f_per = free * 100 // total
		a_per = avail * 100 // total
		full_text = 'M:' + str(f_per) + '/' + str(a_per)
		warn_sig = False
		if dirty_flag:
			if dirty < dirty_down_thresh:
				dirty_flag = False
		if dirty > dirty_up_thresh:
			full_text += '-' + str(dirty // 1000)
			warn_sig = True
			dirty_flag = True
		if a_per < 10:
			warn_sig = True
		result = {'full_text': full_text}
		if warn_sig:
			result['color'] = '#FF0000'
		mystatus['memory'] = result
	except FileNotFoundError:
		pass

def module_busydisk():
	global disk_dict
	new_disk_dict = {}
	mystatus.pop('busydisk', None)
	busy_thresh = 0.1 # SSD should have low threshold value
	busy_string = ""
	for filename in os.listdir('/sys/block'):
		try:
			with open('/sys/block/' + filename + '/stat', 'r') as f:
				new_value = int(f.readline().split()[9])
				if filename in disk_dict.keys():
					old_value = disk_dict[filename]
					if new_value - old_value > sleep_time * 1000 * busy_thresh:
						busy_string += filename + ' '
				new_disk_dict[filename] = new_value
		except:
			pass
	if busy_string:
		mystatus['busydisk'] = {
			'full_text': 'BD:' + busy_string[:-1],
			'color': '#FF0000',
		}
	disk_dict = new_disk_dict

def get_ip_address(ifname):
	data = netifaces.ifaddresses(ifname)[2][0]
	return data['addr'] + '/' + str(IPAddress(data['netmask']).netmask_bits())

def module_default_gateway():
	mystatus.pop('default_gateway', None)
	try:
		with open('/proc/net/route', 'r') as f:
			route = f.read()
			default_nic_search = re.search(r'^([^\t]*)\t0{8}\t[^\t]*', route, flags = re.M)
			if not default_nic_search:
				return
			default_nic = default_nic_search.groups()[0]
			result = {"full_text": default_nic + ':' + get_ip_address(default_nic)}
			mystatus['default_gateway'] = result
	except FileNotFoundError:
		pass

def module_battery():
	mystatus.pop('battery', None)
	try:
		with open('/sys/class/power_supply/BAT0/capacity', 'r') as f:
			line = f.readline()
			bat = int(line)
			result = {"full_text": "B:" + str(bat)}
			if bat < 10:
				result['color'] = '#FF0000'
			mystatus['battery'] = result
	except FileNotFoundError:
		pass

def module_volume(verbose = False):
	global mixer, mixer_list
	mystatus.pop('volume', None)
	if 'Master' not in mixer_list:
		return
	volume = 'V:'
	if not verbose:
		ch_list = ['Master']
	else:
		ch_list = mixer_list
	for channel in ch_list:
		vol_list = mixer[channel].getvolume()
		volume += channel[0] + str(sum(vol_list) // len(vol_list))
		if mixer[channel].getmute()[0] == 1:
			volume += 'M '
		else:
			volume += '% '
	result = {"full_text": volume[:-1]}
	mystatus['volume'] = result

def module_date():
	mystatus.pop('date', None)
	now = datetime.datetime.now()
	date = now.strftime('%m-%d %H:%M')
	result = {"full_text": date}
	mystatus['date'] = result

def calc_module(name):
	globals().get('module_' + name)()

module_list = [
	'cpufreq',
	'cputemp',
	'memory',
	'busydisk',
	'default_gateway',
	'battery',
	'volume',
	'date',
]

def update_modules():
	for module in module_list:
		calc_module(module)

def flush_status():
	print(json.dumps(
		[mystatus[key] for key in module_list if key in mystatus.keys()],
		separators = (',', ':'),
	) + ',', flush = True)

def main_loop():
	global flush_flag
	while True:
		sleep(sleep_time)
		if flush_flag:
			flush_flag = False
			continue
		update_modules()
		flush_status()

def main():
	global mixer, mixer_list
	global fifoid
	signal.signal(signal.SIGRTMIN, flush_volume)
	signal.signal(signal.SIGCONT, flush_all)
	fifo_path = os.environ['XDG_DATA_HOME'] + '/mystatus/fifo'
	pid_path = os.environ['XDG_DATA_HOME'] + '/mystatus/pid'
	try:
		os.mkfifo(fifo_path)
	except FileExistsError:
		pass
	fifoid = os.open(
		fifo_path,
		os.O_RDONLY | os.O_NONBLOCK,
	)
	print(os.getpid(), file = open(pid_path, 'w'))
	print('{"version":1}[')
	mixer = dict()
	mixer_list = []
	for mixer_id in ('Master', 'Headphone', 'Speaker'):
		try:
			mixer[mixer_id] = Mixer(mixer_id)
			mixer_list.append(mixer_id)
		except ALSAAudioError:
			pass
	update_modules()
	flush_status()
	main_loop()

if __name__ == '__main__':
	main()
