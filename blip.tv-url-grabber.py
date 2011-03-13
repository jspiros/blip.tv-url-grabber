#!/usr/bin/env python
# encoding: utf-8
"""
blip.tv-url-grabber.py

"""

import sys
import os
import argparse
from urlparse import urljoin
from urllib2 import urlopen
from lxml import etree
import unicodedata
import datetime
import string


def date_string(string):
	cmp = string.split('-')
	return datetime.date(int(cmp[0]), int(cmp[1]), int(cmp[2]))


arg_parser = argparse.ArgumentParser()
arg_parser.add_argument(
	'url',
	help='blip.tv channel to obtain urls from (e.g. http://pycon.blip.tv)'
)
arg_parser.add_argument(
	'--after',
	help='only urls posted after this date will be handled',
	default=None,
	type=date_string
)
arg_parser.add_argument(
	'--ignore_dir',
	help='only urls not downloaded in this directory will be handled',
	default=None
)


class BlipTVChannel(object):
	def __init__(self, url):
		self.url = url
		self.url_handle = urlopen(urljoin(self.url, '/posts/?pagelen=2000&skin=api'))
		self.tree = etree.parse(self.url_handle)
		self.episodes = dict([(element.xpath('./guid/text()')[0], BlipTVEpisode(element)) for element in self.tree.xpath('/response/payload/asset')])


class BlipTVEpisode(object):
	def __init__(self, element):
		self.element = element
		self.name = self.element.xpath('./title/text()')[0]
		self.uuid = self.element.xpath('./guid/text()')[0]
		self.timestamp = int(self.element.xpath('./timestamp/text()')[0])
		self.date = datetime.date.fromtimestamp(self.timestamp/1000)
		self.conversions = [conversion.xpath('./target/text()')[0] for conversion in self.element.xpath('./conversions/conversion')]
		self.media = []
		for media in self.element.xpath('./mediaList/media'):
			new_media = {}
			try:
				new_media['role'] = media.xpath('./role/text()')[0]
			except IndexError:
				pass
			try:
				new_media['url'] = media.xpath('./link/@href')[0]
			except IndexError:
				pass
			try:
				new_media['width'] = media.xpath('./width/text()')[0]
			except IndexError:
				pass
			try:
				new_media['height'] = media.xpath('./height/text()')[0]
			except IndexError:
				pass
			try:
				new_media['type'] = media.xpath('./link/@type')[0]
			except IndexError:
				pass
			try:
				new_media['size'] = int(media.xpath('./size/text()')[0])
			except IndexError:
				pass
			self.media.append(new_media)
	
	@property
	def media_excluding_conversions(self):
		return [media for media in self.media if media['url'][-3:] not in self.conversions]
	
	@property
	def videos(self):
		return [media for media in self.media if media['type'].startswith('video')]
	
	@property
	def videos_excluding_conversions(self):
		return [media for media in self.videos if media['url'][-3:] not in self.conversions]


def best_video_url_and_size_for_episode(episode):
	ranked = [] # list of tuples, (object, ranking)
	for media in episode.videos_excluding_conversions:
		ranking = 0
		if media['role'].startswith('Web'):
			ranking = ranking - 1
		elif media['role'] == 'Source':
			ranking = ranking + 1
		elif media['role'] == 'Master':
			ranking = ranking + 2
		if media['type'] == 'video/x-flv':
			ranking = ranking - 1
		elif media['type'] == 'video/ogg':
			ranking = ranking + 1
		ranked.append((media, ranking))
	ranked.sort(key=lambda rank: rank[1])
	
	chosen = ranked[-1][0]
	
	return chosen['url'], chosen['size']


def filename_and_url_and_size_for_episode(episode):
	""" Returns a tuple containing the ideal video filename for an episode, and the URL at which the file's contents can be obtained. """
	
	valid_chars = '-_.,:;()#[]" %s%s' % (string.ascii_letters, string.digits)
	
	url, size = best_video_url_and_size_for_episode(episode)
	extension = url.split('.')[-1]
	name = unicode(episode.name)
	
	name = name.replace(':', ' - ')
	name = name.replace('  ', ' ')
	name = name.replace('`', '"')
	name = name.replace('\'', '"')
	name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore')
	name = ''.join(c for c in name if c in valid_chars)
	name = name.strip('. ')
	
	return "%s.%s.%s.%s" % (episode.date.isoformat(), name, episode.uuid, extension), url, size


if __name__ == '__main__':
	args = arg_parser.parse_args()
	ignore_uuids = []
	if args.ignore_dir:
		ignore_uuids = [filename.split('.')[-2] for filename in os.listdir(args.ignore_dir)]
	channel = BlipTVChannel(args.url)
	total_size = 0
	print "#!/bin/bash"
	for uuid, episode in channel.episodes.items():
		if args.after:
			if episode.date < args.after:
				continue
		if ignore_uuids:
			if episode.uuid in ignore_uuids:
				continue
		filename, url, size = filename_and_url_and_size_for_episode(episode)
		total_size += size
		
		context = {'filename': filename, 'url': url}
		
		print "echo Downloading from %(url)s" % context
		print "curl -L -o '%(filename)s' %(url)s" % context
	print "# Total size of all files: %i MiB" % (total_size / 1024 / 1024)
