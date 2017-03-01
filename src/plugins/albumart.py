# -*- coding: utf-8 -*-
################################################################################
#  Copyright (C) 2007  Travis Shirk <travis@pobox.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
################################################################################
import urllib, time

import amazon
amazon.setLicense('0XMTPCQ85ZMFF2PAT402')

import mesk
import mesk.plugin
from mesk.i18n import _
from mesk.plugin.plugin import PluginInfo, Plugin
from mesk.plugin.interfaces import MetaDataSearch

def soundex(name, len=6):
    # digits holds the soundex values for the alphabet
    digits = '01230120022455012623010202'
    sndx = ''
    fc = ''

    # translate alpha chars in name to soundex digits
    for c in name.upper():
        if c.isalpha():
            if not fc:
                fc = c   # remember first letter
            try:
                d = digits[ord(c)-ord('A')]
            except IndexError, ex:
                # Most likely c is not an ascii character
                mesk.log.warning("Invalid character '%s' (%x) in soundex "
                                 "algorithm, skipping" % (c, ord(c)))
                continue
            # duplicate consecutive soundex digits are skipped
            if not sndx or (d != sndx[-1]):
                sndx += d

    sndx = fc + sndx[1:]   # replace first digit with first char
    sndx = sndx.replace('0','')       # remove all 0s
    return (sndx + (len * '0'))[:len] # padded to len characters

class AmazonAlbum(object):
   # Image sizes
   IMG_SMALL  = 0x1;
   IMG_MEDIUM = 0x2;
   IMG_LARGE  = 0x4;

   def __init__(self, bag):
      self.bag = bag;

   def get_title(self):
      return self.bag.ProductName.encode("utf-8");

   def get_artists(self):
      try:
          if type(self.bag.Artists.Artist) is list:
              return [a.encode("utf-8") for a in self.bag.Artists.Artist]
          else:
              return [self.bag.Artists.Artist.encode("utf-8")]
      except AttributeError:
          return []

   def get_release_date(self):
      if hasattr(self.bag, "ReleaseDate"):
         return self.bag.ReleaseDate.encode("utf-8");
      else:
         return None;

   def get_label(self):
      if hasattr(self.bag, "Manufacturer"):
         return self.bag.Manufacturer.encode("utf-8");
      else:
         return None;

   def get_num_tracks(self):
      t = self.get_tracks();
      if t:
         return len(t);
      else:
         return 0;

   def get_tracks(self):
      if hasattr(self.bag, "Tracks"):
         tracks = [];
         for t in self.bag.Tracks.Track:
            tracks.append(t.encode("utf-8"));
         return tracks;
      else:
         return None;

   def get_img_url(self, size):
      if size == self.IMG_SMALL and hasattr(self.bag, "ImageUrlSmall"):
         return self.bag.ImageUrlSmall.encode("utf-8");
      elif size == self.IMG_MEDIUM and hasattr(self.bag, "ImageUrlMedium"):
         return self.bag.ImageUrlMedium.encode("utf-8");
      elif size == self.IMG_LARGE and hasattr(self.bag, "ImageUrlLarge"):
         return self.bag.ImageUrlLarge.encode("utf-8");
      else:
         return None;

   def get_amazon_url(self):
      return self.bag.URL.encode("utf-8");

   def get_amazon_price(self):
       try:
           return self.bag.OurPrice.encode("utf-8");
       except AttributeError:
           return None;

   def get_used_price(self):
      if hasattr(self.bag, "UsedPrice"):
         return self.bag.UsedPrice.encode("utf-8");
      else:
         return None;

   def __str__(self):
      s = "";
      s += "\nTitle: %s" % self.get_title();
      s += "\nArtists:\n"
      for a in self.get_artists():
          s += "\t%s\n" % a

      s += "\nRelease Date: %s" % self.get_release_date();
      s += "\nLabel: %s" % self.get_label();
      s += "\nTracks:"
      c = 1;
      n = self.get_num_tracks();
      tracks = self.get_tracks();
      if tracks:
         for t in tracks:
            s += "\n\t(%d/%d) %s" % (c, n, t)
            c += 1;
      else:
         s += "\nNo tracks! :(";
      s += "\nImage URL (Large): %s" % self.get_img_url(self.IMG_LARGE);
      s += "\nImage URL (Medium): %s" % self.get_img_url(self.IMG_MEDIUM);
      s += "\nImage URL (Small): %s" % self.get_img_url(self.IMG_SMALL);
      s += "\nAmazon Price: %s" % self.get_amazon_price();
      s += "\nUsed Price: %s" % self.get_used_price();
      s += "\nSee Amazon: %s" % self.get_amazon_url();
      # XXX: There is a lot of other stuff in the amazon search result.
      # See the README
      return s;


MAX_SEARCH_RESULTS = 25
MAX_CACHE_SIZE = 8
class AlbumArtPlugin(Plugin, MetaDataSearch):
    def __init__(self):
        Plugin.__init__(self, PLUGIN_INFO)
        MetaDataSearch.__init__(self, MetaDataSearch.CAP_ALBUM_ART)
        self._cache = {}  # query: (last_time, {cap: img})

    def plugin_metadata_search(self, artist, album, track):
        artist = artist.lower()
        artist_soundex = soundex(artist)
        query = artist.encode('utf-8')

        if album:
            album = album.lower()
            query += ' %s ' % album.encode('utf-8')
        album_soundex  = soundex(album)

        # Check cache
        if self._cache.has_key(query):
            self.log.debug("Returning cached album cover: %s" % query)
            retval = self._cache[query][1]
            retval[0] = time.time()
            self._cache[query] = (time.time(), retval)
            return retval

        self.log.debug("Searching amazon.com: %s" % query)
        results = amazon.OnDemandAmazonList(amazon.searchByKeyword,
                                            {'keyword': query,
                                             'product_line': 'music'})
        search_match = None
        search_fuzzy_matches = {}

        result_count = 0
        for result in results:
            if search_match:
                # Found a match, bail
                break

            result_count += 1
            if result_count > MAX_SEARCH_RESULTS:
                # Stop looking, there could be hundreds and each batch hits the
                # network
                self.log.verbose("No album cover found for artist: %s,"
                                                           "album: %s" %
                                 (artist, album))
                break

            amazon_album = AmazonAlbum(result)
            self.log.debug("Amazon result:\n%s" % str(amazon_album))

            am_artists = amazon_album.get_artists()
            am_artists = [a.lower() for a in am_artists]
            am_album = amazon_album.get_title().lower()

            if artist in am_artists and album == am_album:
                # Definite match
                self.log.debug("albumart found exact match")
                search_match = amazon_album
            else:
                # Fuzzy matching results go into an ordered list

                # Compare soundex values and insert fuzzy matches in priority
                # order
                am_artist_soundex = [soundex(a) for a in am_artists]
                am_album_soundex = soundex(am_album)
                if (artist_soundex in am_artist_soundex and
                        album == am_album):
                    self.log.debug("amazon artist soundex AND album match")
                    search_fuzzy_matches[1] = amazon_album
                elif (artist in am_artists and
                        album_soundex == am_album_soundex):
                    self.log.debug("amazon artist match AND album soundex")
                    search_fuzzy_matches[2] = amazon_album
                elif (artist_soundex in am_artist_soundex and
                        album_soundex == am_album_soundex):
                    self.log.debug("amazon artist soundex AND album soundex")
                    search_fuzzy_matches[3] = amazon_album
                    found = True
                elif (artist_soundex in am_artist_soundex) or \
                        (album_soundex == am_album_soundex):
                    self.log.debug("amazon artist soundex OR album soundex")
                    search_fuzzy_matches[4] = amazon_album
                else:
                    continue

        if not search_match and search_fuzzy_matches:
            # No exact match, use highest prority fuzzy result
            keys = search_fuzzy_matches.keys()
            keys.sort()
            search_match = search_fuzzy_matches[keys[0]]

        cover_image = None
        if search_match:
            for url in [search_match.get_img_url(AmazonAlbum.IMG_LARGE),
                        search_match.get_img_url(AmazonAlbum.IMG_MEDIUM),
                        search_match.get_img_url(AmazonAlbum.IMG_SMALL)]:
                img = self._fetch_image(url)
                if img and len(img) == 807:
                    # 807 is the size of an empty image result from amazon
                    continue
                elif img:
                    # Got a cover
                    cover_image = img
                    break
        else:
            self.log.debug("amazon.com no match found")

        if not cover_image:
            self.log.debug("amazon.com no image available")

        retval = {MetaDataSearch.CAP_ALBUM_ART: cover_image}

        # Update/clean cache
        now = time.time()
        self._cache[query] = (now, retval)

        # Prune cache
        cached_keys = []
        for key in self._cache:
            if self._cache[key][1][1]:
                # Only add if there is an image, this is the mem being saved
                cached_keys.append(key)

        if len(cached_keys) > MAX_CACHE_SIZE:
            access_times_to_keys = {}
            for key in cached_keys:
                access_times_to_keys[self._cache[key][0]] = key
            times = access_times_to_keys.keys()
            times.sort()

            size = len(cached_keys)
            while size > MAX_CACHE_SIZE:
                t = times.pop(0)
                key = access_times_to_keys[t]
                self.log.debug('Removing \'%s\' from album cover cache' % key)
                size -= 1
                del self._cache[key]

        return retval

    def _fetch_image(self, url):
        if not url:
            return None
        else:
            self.log.debug("Fetching image URL: " + url)
            resp = urllib.urlopen(url)
            img_data = resp.read()
            resp.close()
            return img_data

XPM = [
"150 60 158 2",
"  	c #030303",
". 	c #070708",
"+ 	c #080707",
"@ 	c #090708",
"# 	c #0C0B0B",
"$ 	c #110E0F",
"% 	c #120F10",
"& 	c #141212",
"* 	c #191616",
"= 	c #1A1718",
"- 	c #1D1A1B",
"; 	c #211D1E",
"> 	c #221F20",
", 	c #21201F",
"' 	c #252223",
") 	c #282626",
"! 	c #2A2728",
"~ 	c #2C2B2C",
"{ 	c #312E2F",
"] 	c #312F30",
"^ 	c #333233",
"/ 	c #383637",
"( 	c #393738",
"_ 	c #3C3B3C",
": 	c #403E3E",
"< 	c #413F40",
"[ 	c #444343",
"} 	c #484647",
"| 	c #4A4748",
"1 	c #4D4B4C",
"2 	c #504E4F",
"3 	c #504F50",
"4 	c #545354",
"5 	c #575857",
"6 	c #585757",
"7 	c #595758",
"8 	c #5B5A5B",
"9 	c #625F5D",
"0 	c #636263",
"a 	c #686766",
"b 	c #6A6966",
"c 	c #6D6B6C",
"d 	c #706E6D",
"e 	c #706F70",
"f 	c #747374",
"g 	c #787676",
"h 	c #797778",
"i 	c #797876",
"j 	c #7D7C7C",
"k 	c #807F7E",
"l 	c #817F80",
"m 	c #F7A505",
"n 	c #F7A709",
"o 	c #F7A80D",
"p 	c #F7AA13",
"q 	c #F7AD1A",
"r 	c #F8AB16",
"s 	c #F8AE1D",
"t 	c #F7AF21",
"u 	c #F8AF21",
"v 	c #F7B023",
"w 	c #F8B124",
"x 	c #F8B42C",
"y 	c #F8B633",
"z 	c #F8B738",
"A 	c #F8B93A",
"B 	c #F9BC44",
"C 	c #F9BF4C",
"D 	c #F9C04F",
"E 	c #F9C253",
"F 	c #F9C55D",
"G 	c #F9C662",
"H 	c #FAC866",
"I 	c #F9CA6C",
"J 	c #FACD75",
"K 	c #FACF7C",
"L 	c #FBD17E",
"M 	c #848383",
"N 	c #888687",
"O 	c #898788",
"P 	c #8A8886",
"Q 	c #8C8B8C",
"R 	c #908F8F",
"S 	c #908F90",
"T 	c #94928C",
"U 	c #949394",
"V 	c #989697",
"W 	c #989798",
"X 	c #9C9B9B",
"Y 	c #A09E9D",
"Z 	c #A19FA0",
"` 	c #A5A29C",
" .	c #A4A3A4",
"..	c #A8A7A7",
"+.	c #A9A7A8",
"@.	c #ACABAB",
"#.	c #B1AEA7",
"$.	c #B0AFAF",
"%.	c #B1AFB0",
"&.	c #B5B2AE",
"*.	c #B3B3B3",
"=.	c #B8B7B7",
"-.	c #B8B7B8",
";.	c #BCB8B2",
">.	c #BCBBBB",
",.	c #C0BFBF",
"'.	c #C0BFC0",
").	c #C5C2BD",
"!.	c #FBD383",
"~.	c #FBD68B",
"{.	c #FBD88F",
"].	c #FCD791",
"^.	c #FBD994",
"/.	c #FBDB9B",
"(.	c #FCDEA3",
"_.	c #FCE0A7",
":.	c #FCE1AC",
"<.	c #FCE4B3",
"[.	c #FDE7BB",
"}.	c #FDE8BD",
"|.	c #C5C4C5",
"1.	c #C8C7C7",
"2.	c #C8C7C8",
"3.	c #CBC9C7",
"4.	c #CCCCCC",
"5.	c #D1CECC",
"6.	c #D1CFD0",
"7.	c #D3D2CF",
"8.	c #D3D3D3",
"9.	c #D9D7D4",
"0.	c #DBD9D7",
"a.	c #DCDBDB",
"b.	c #E0DEDF",
"c.	c #E0DFE0",
"d.	c #E3E0DA",
"e.	c #FDEAC4",
"f.	c #FDEDCC",
"g.	c #FCEED3",
"h.	c #FAEFDB",
"i.	c #FDF0D6",
"j.	c #FDF2DC",
"k.	c #E3E3E3",
"l.	c #E8E7E6",
"m.	c #E8E7E8",
"n.	c #EBE9E4",
"o.	c #ECEBEC",
"p.	c #F0EDE7",
"q.	c #F2EFEB",
"r.	c #F6F3EC",
"s.	c #FEF6E5",
"t.	c #FEF7E9",
"u.	c #FEF8EC",
"v.	c #F4F4F4",
"w.	c #F7F7F8",
"x.	c #F9F7F6",
"y.	c #F8F7F8",
"z.	c #FEFBF4",
"A.	c #FFFFFF",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.t.g.e./.<.e.j.z.A.A.A.A.A.A.A.A.A.A.A.t.e.}./.}.f.u.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.j.<.<.J x o n n o C ^.<.e.z.A.A.A.A.A.e.:.{.H p n n n r J <.<.j.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.}.I y m m n o o n m o A !.u.A.A.A.A.A.{.C q m n o o n m m y I }.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.s.(.:.s.A.e.!.J y n n A J ~.j.A.f.<.z.f.].[.A.z.(.K B o m y F !.e.A.i./.e.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.s.C q E K :.s.y.e.~.~.f.A.j./.K A F z.K m y J !.e.A.i.{.~.[.z.A.:.L D n J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.y.I m m m t C J <.A.A.(.I C p m m I A.L m n m m y I L y.A.e.K I w m n m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m o o t o n x r.h.w m n o o m I A.L m n o s p m n {.s.A m m o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.y.I m o o q o o r h.j.p o o o o m I A.L m o o p o o o K s.x o o o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m o o o o o q h.h.r o o o o m F z.L m o o o o n p ~.s.z o o o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m o o o o o q h.s.r o o o o n B i.!.m o o o o o p ~.s.z o o o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m o o o o o q h.g.r o o o o m B g.!.m o o o o o p ~.s.z o o o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.y.I m o o t p o q h.g.r o o o o n B g.!.m o o o o o p ~.s.z o o o o o m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m p o o o o q h.g.p o o o o m B g.!.m o o o o o p ~.s.z o o o o o m K A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.I m s p o o o q h.g.p p p o o n B g.!.m n o o o o p ~.s.z o o o o n m J A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.{.z y q n n o q h.g.p p t n p w H i.:.B x p n n n p ~.s.z o o n o u z ].A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.s.i.u.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.u.g.h.A.s.~.C B t p h.g.p m q A I f.A.A.A.A.f.H B v o o ~.s.y n o y F <.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.z.e.<.(.H B I _.}.i.A.A.A.A.A.A.A.A.A.i.[.:.K x B /.<.f.u.x.(.H s.g.t F ~.s.A.A.A.A.A.A.A.A.A.(.G A ~.s.y B H e.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.u.(.J v m n n n n m p B /.j.A.A.A.A.A.i.~.B p m m o o m m w I e.A.A.A.u.^.A.A.A.A.A.A.A.A.A.A.A.A.A.A.e.[.z.:.s.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.s.z.u.!.J F q m n n m p B I ~.i.y.y.z.f.A.f.J I B o m m m m u G J <.A.i.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"z.(.I {.f.y.z.(.!.F A I ^.i.A.j.^.!.g.s.B !.^.s.A.g.].K C C K (.A.z._.~.F u.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"z.!.n o y G ~.f.A.s.f.z.z./.J C o p f.s.p m p D J ^.t.A.g.i.A.f.!.F v n p u.A.A.A.A.A.A.v.-.l c c c N |.A.A.A.A.A.x.|.|.,.1.A.q. .Q Q X o.A.A.y...V V Y A.A.A.A.A.A.A.A.k.+.j c e c Q 4.A.A.A.A.A.q.=.|.|.|.|.|.|.|.|.|.|.v.A.A.A.A.A.+.N V U @.o.A.A.A.A.A.c.2.|.=.l.A.o.X V U =.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"z.!.p o n m p z E <.A.(.E q m n o q j.s.p o o o m r D ~.s.[.I z o m n o q u.A.A.A.A.A.6.3 ^ = # # # - ( 7 m.A.A.A.k._ ^ ~ 0 9.6 = & ; ; 4 9.o.e - ' ) = a k.A.A.A.A.v...} ~ * # # # > _ f w.A.A.A.7.) ^ ] ^ ] ] ^ ^ ^ ^ _ a.A.A.A.=.7 ' - ) ; ' 1 @.A.A.A.A.j / ] ~ i n.5 ) ' ; ) U A.A.A.A.A.A.A.A.A.A.A.A.",
"z.!.o o o o n n m !.w.G m o o o o q h.s.p o o p v n m B i.~.o m o o o o q u.A.A.A.A.6.^ $ * ; & * > - &   4 o.A.A.c.. % % : d   & * ; *   S 0 * & - - & & 8 A.A.A.A. .> $ = - $ = > - % . j w.A.A.|.  & & % & % % % $ $ ~ a.A.A.Z ~ $ & ; - - & & ) @.A.A.A.b * % & _ [ & ; ; = & = U A.A.A.A.A.A.A.A.A.A.A.",
"z.!.p o o o o o m K w.H m o o o o p j.s.p p w p p o m C i.{.r o o o o o q u.A.A.A.m.c   ; ; $ ^ ( # * ; * # 4.A.A.c.# ; ; ' ) $ + & ; ; = ' = # + = ; ; = = >.A.A.-.; * > & & } - # = - = , q.A.A.1.  + + + . & ; ; ; # / a.A.k.~ & ; = & ^ & $ ; * { -.A.A.f ' ; ; ' & + # ; ; ; # 1 o.A.A.A.A.A.A.A.A.A.A.",
"z.!.p o o o o q q !.w.H m o o o o q j.t.p o p o o o m B i.{.r n o o o o q u.A.A.A.2.& - ; = f a.a.W ) * ; . j v.A.k.# ; ; - - 2 c - & ; ; * # ] j { ; ; = # f A.A.V   ; & - W c.9.7 ' ; - & 8.A.A.v.).-.-.|...^ % ; ; . +.y.y.f - - * ~ 5.a. .; # ' . V A.A.f ' ; ; - & f g $ ; ; $ / 3.A.A.A.A.A.A.A.A.A.A.",
"z.!.o o o o o o n K w.G m o o o o q h.s.p o o o o o o B i.{.r n o o o o q u.A.A.A.4.= # $ 5 m.A.A.q.[ $ ; . j v.A.k.# - ; & 1 o.q.M = - > # 1 4.v.0.- - - ; b A.A.$.& # # N w.A.A...- = - & 9.A.A.A.A.A.A.z.S & - ; # 8 k.A.v.' - ; - | A.A.v.M   ; # 1 9.A.f ' - ; # l o.o.Q + ; $ ^ |.A.A.A.A.A.A.A.A.A.A.",
"z.!.p o o o o o m K w.G n o o o o p h.s.p o o o o o n B i.{.r o o o o o q u.A.A.A.y.o.k.k.m.v.q.q.o.| % ; . k v.A.c.# - - > M A.A.9.[ % >   #.A.A.v.- - ; ' b A.A.v.k.k.k.o.v.q.o.*.; = - & a.A.A.A.A.A.A.X & = ; - $ *.A.A.4.= - - = @.A.A.A.X   ; - = $.A.f ' ; - % k.A.A.4.  ; $ / |.A.A.A.A.A.A.A.A.A.A.",
"z.!.p p o o o o m !.w.G m o o o o q h.s.p o o o o o n B i.{.r o o o o o q u.A.A.A.A.A.w.9. .c _ - & * ; ; + k v.A.k.# ; & - ..A.A.4._ # >   ;.A.A.v.= - ; > c A.A.A.A.v.|.N 8 ) & & = ; - & a.A.A.A.A.A.a.1 # - - % ..y.A.A.Y % - = & X A.A.A. .@ ; ;    .A.g ' - ; & o.A.A.4.. ; % ^ |.A.A.A.A.A.A.A.A.A.A.",
"z.L r w o o o o m !.A.G n o o o o q g.s.p o o o o o o B i.{.p o o o o o q u.A.A.A.A.v.T # # & = - ' ; ; ; + M v.A.k.# ; & ) -.A.A.4._ $ >   ,.A.A.v.= - ; > b A.A.y.4.5 # # & * - - - ; ; & a.A.A.A.A.v.Q # - - # j v.A.A.A.X % - = ' r.A.A.A.=.{ ; ;    .A.g ' ; ; ] o.A.A.4.. ; % ^ |.A.A.A.A.A.A.A.A.A.A.",
"z.L v m n o o o m !.y.H n o o o n t e.t.y p n n o o n B i.{.p o o o n n y u.A.A.A.v.l # ; - = ~ 4 b ] - ; + M v.A.c.# ; & ) -.A.A.4._ # ;   ,.A.A.v.= ; ; > b A.A.3.( $ ; = ) ^ 7 } - - - & a.A.A.A.w.W + ; ; # ^ |.A.A.A.A.X & = = ' d.A.A.A.=.~ - ;    .A.g > ; ; 1 q.A.A.4.. ; $ ^ |.A.A.A.A.A.A.A.A.A.A.",
"A.z./.B y p n n m !.A.G m n n v B ~.z.A.e.G B v m n m C g.{.p n n q B C e.A.A.A.A.*.. ; - & b l.A.A.1 % ; + k v.A.k.# - & ) -.A.A.5._ $ ; . ,.A.A.v.= - ; > c A.v.h . ; = - %.A.A.'., = - & a.A.A.A.|.' $ ; * ) *.A.A.A.A.A.W % - = & U A.A.A...& ; ;    .A.g > - ; 1 v.A.A.4.. ; $ ^ |.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.f.!.C v m K y.F p A E (.A.A.A.i.z.A.A./.E z p z f.~.n v C !.z.A.A.A.A.A.o.j . ; # _ 8.A.A.v.[ % ; . Q v.A.k.# ; & ) -.A.A.4._ $ ; . '.A.A.v.= - ; > b A.|.- % ; + h v.A.A...* = - & k.A.A.o.c # ; ; # c ).4.k.A.A.A.%.& - - = U A.A.A.Y   ; ; % ..A.g > - ; | v.A.A.4.  ; % ^ 1.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.u.^.E /.y./.~.g.A.z.}._./.D !._.[.s.A.f.!.K i.(.F /.z.A.A.A.A.A.A.A.o.c . ; # 7 v.A.A.-.~ * ; $ 0 v.A.k.# - & ) -.A.A.4._ # ;   >.A.A.v.= ; ; > b A.,.' - ; . U A.A.A.f * = - & 2.A.v. .  > ; - ; ~ ' ^ 8 U |.w.o.= - - - 4 A.A.v.N   ; * ( 2.A.g ' - ; 1 q.A.A.4.. ; $ ^ |.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.z.t.A.A.A.<.~.J v m m o m o v F ~.[.A.A.A.A.A.A.A.A.A.A.A.A.A.A.m.0 + ; * ~ *.A.9.[ * ; ; ; . 3.A.c.# - & ) -.A.A.4._ $ ; . >.A.A.v.= - ; > c A.|.' ; ; $ 7 b.A.>.~ * ; - & 4 A.k._ $ ; ; ; ; - ; & # . ] a.z.1 & ; * - |.A.|.{ & >   c o.A.f ' ; ; 1 v.A.A.3.. ; % ^ 1.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.u.A.A.(.K C o m n o o m p E L :.A.z.u.A.A.A.A.A.A.A.A.A.A.A.v.R + ; ; % [ j [ % + = ; - & 4 v.c.# ; & ) -.A.A.4._ $ ;   ,.A.A.v.- - ; > c A.8._ & ; ; * 6 j / - # - - - # U 0.~ ; ; * # + + . # = ;   ).A.|.# - - & : j 1 $ ; & ~ >.A.A.g ' - ; 1 v.A.A.4.. ; % ^ |.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.(.H !.g.A.s.(.^.D o B ~.(.t.A.f.L ~.i.A.A.A.A.A.A.A.A.A.A.A.A.3.+ $ ; ; & #     7 ) = ; # N v.k.# - & ) -.A.A.4._ $ ; . >.A.A.v.= ; ; ' b A.y.Q   ; ; ; % # # & 3 = = # . Z a.' + # ~ 5 c P b ^ # .   *.A.z.Q # $ ; * # % > & # N v.A.A.g ' - > 1 v.A.A.4.. ; $ ^ |.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.!.m o A G /.j.A.s.:.f.A.i.^.F z m B f.A.A.A.A.A.A.A.A.A.A.A.A.o.N * . .   . . c c.X - . Q A.A.c.  .   - @.A.A.|.]   .   >.A.A.v.& .   # 0 A.A.a.a @   . . + = Q a.[ . ~  .A.k.8 8  .>.a.v.A.o.2...h ' |.A.A.A.V $ . + @ +   ~ U k.A.A.A.9 +   . ] q.A.A.3.  .   ) >.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p n n n s A F L A.f.E A s m o n B f.A.A.A.A.A.A.A.A.A.A.A.A.A.v.>...V W  .*.o.A.v.$.@.y.A.A.v.@.V W ..k.A.A.o.@.W W +.o.A.A.A.=.W X X 8.A.A.A.o.$.X X V  .>.w.A.4. .2.A.A.y.a.k.A.A.A.A.A.A.A.A.v.|.v.A.A.A.A.>. .f 7 0 ..3.y.A.A.A.A.3.X X W -.y.A.A.v.+.W W @.o.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p o o o n o n v s.~.o v o o o n B f.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.y.A.A.A.A.A.A.A.A.A.A.A.A.y.A.A.A.A.o.o.A.y.A.A.A.A.A.A.A.y.A.A.A.A.A.A.A.A.A.A.y.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.o.A.A.A.A.A.o.k.o.A.A.A.A.A.A.A.A.A.A.y.A.A.A.A.A.A.A.y.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p t p o o o o s s.!.o p o o o n B f.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.b.b ~  .A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.5 { X w.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p p p o o o o t s.!.o o o o o n C f.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.9.1   P A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.^   4 v.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p o o o o o o s s.!.p o o o o n B f.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.v.v.v.y.A.A.a.1   Q z.y.y.A.A.A.A.A.A.A.A.A.v.z.A.A.A.A.A.A.A.w.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.8.M c.A.A.A.y.x.A.A.A.A.A.A.A.A.y.y.A.A.A.A.A.A.A.z.x.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.{.p o o o o o o s t.!.o o o o p o B f.A.A.A.A.A.A.A.A.A.A.A.A.w.a.6.v.A.A.8.6.v.A.A.o.>.v.A.a.3 } 1 R o.A.a.1   l =.N N 4.y.A.A.A.A.w.k.-.j -.o.w.A.A.A.o.|.M  .a.w.A.A.k.m.v.9.8.v.8.1.v.A.A.A.o.8.v.o.9.o.A.A.k.|.U |.o.z.A.A.A.r.2.N U 9.w.A.A.A.v.c.+.M |.o.A.v.k.l.k.o.o.y.A.o.v.A.",
"A.A.A.A.A.A.A.A.A.A.^.q o o o o o o s s.!.o o o o q s B f.A.A.A.A.A.A.A.A.A.A.A.A.4.* * Q A.k.7 . ..A.A._ . 4.'.= . ; = . } k.a.1 # * . # # # *.y.A.A.y.X & . # . ~ ` v.A.9.| + # . $ U w.m.* ) Q + ^ M & = X A.A.v.4 . |._ # i v.|.$ . . . _ 8.A.A.o.0 . # # # U v.A.o.0 # . # + [ 9.@.~ > ) 0 ) *.v.^ l v.",
"A.A.A.A.A.A.A.A.A.A.e.A n o o o o o s s.!.o o o o o n B f.A.A.A.A.A.A.A.A.A.A.A.A.o.f   8 A.-.{   W A.v.^ # 3.- * [ a.@.' # 8 k.1 # # - f < * # 4.A.A.8.# = _ 7 ~ # , @.o.8 # ) 5 < * # 4.a.% =   & 2 Y 1   f z.A.=.) # 3.^   Q a.$   ' [ ~ # 4 o.o.0 + ) 5 4 - # &.v.V # ; _ 7 ~ + 4 l.8.[ V $.- } X ' c v.",
"A.A.A.A.A.A.A.A.A.A.f.B m n o p o o s s.!.p o o o n m D i.A.A.A.A.A.A.A.A.A.A.A.A.A.+.  1 v.T & # 8 k.*.- 1 N $ ' r.A.A...  1 8.3 . ^ -.A.1.~   V v.y.f   ~ A.A.7._ ~ X U % - >.A.A.5 . 5 c.& * % Q v.q.f   5 k.A.M # 8 k.^   W  .. * -.A.|.# # U ..& & =.A.A.0 = ; a.[   : A.A.|.~ 4 3.v.4 V $.~   # _ b q.",
"A.A.A.A.A.A.A.A.A.A.t./.F y o s p o s s.!.o o m p B D /.A.A.A.A.A.A.A.A.A.A.A.A.A.A.>.# ~ >.P + ; ' |.c #  .[ # [ +.*.*.N . ~  .9   P A.A.A.[   6 o.y.O . ' *.3.k.k.9.y.e   7 -.3.2.U - # 4.% * 5 A.A.A.+.# ~ @.y.5   R v.^   V 0 . ^ A.A.k.e ) X N   1 @.1.1.@.' + 0.: . ^ *.5.k.9.k.A.o.4 V *.1 ~ ' Q 0 o.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.}.J E s m q s.!.m p E L i.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.9._ # M j # '   @.[   6.) = #           ' X 0   Q A.A.A.0 . _ o.A.3.# # # / 7 U 4.b.| # ' ' - - # # .  .# - 8.A.A.A.4._   N k.< # |.A.{   X ] # l A.A.A.a.=.k.k @ ' ' - ; ; $   5. .  +   ( c Y 3.A.y. .|.9.V @.*.=.$.w.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.t./.J B t./.J {.u.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.v.M   ( _ } 1 # 0 { # 8.' & [ c c c c f N *.6   Q A.A.A.g # _ l.A.v.k [ '       _  .4 . _ 8 0 0 0 b a -.# , q.A.A.A.v.h   j ..= [ a.A.{ . +.* %  .A.A.A.A.A.A.f . : 0 9 0 0 b 0 a.v.f [ &       _ 8.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.}.A.s.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.@.  *   N Y ' & $ _ a.~ . 0 A.A.A.A.4.b.a.1   Q A.A.A.7 . 2 o.A.A.A.9.X k 0 *   4 0   Q w.z.y.A.x.A.k.# , k.A.A.A.A.X # 4 1   U v.A.~ . X / # f A.A.A.3.k |.l   h q.y.y.A.x.A.A.A.v.0.X j 9 & $ l A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.=.& & . Q k._ $ . j o.0 . - a.A.A.>./ 0 2.5   f v.A.A._   j v.v.M c @.A.A.r.f   a c   0 o.A.A.6.c e 9.# , m.A.A.A.A.'.] = )   @.A.A.^   V c . _ A.A.a.[   k Q   [ 8.A.A.c.f c k.f 0 l.A.A.a.1   d A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.a.1 + - X x.4 $ . -.A.4.& * 3 +.W _   [ 6.4 . ' V y.S '   >.A.v.^   ~ >.A.a.4 . i X # * j q.6.1   ' a.$ , k.A.A.A.A.q.d . & ~ |.A.A.~   Q |.. - Q v.j   ) -.@., % 8 k.k.8 . # 9.. & 5 1.A.3.{ + c A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.x.U   ^ -.A.b . # 4.A.A.W #   > *   / 4.8.<     = | ' . f v.A.y.=.    ~ 1 (   -  .k.4   & [ ^     $.a.# , c.A.A.A.A.A.N     h v.A.A.]   f o.3 # ' [ *   4 w.o.0   . _ _ .    .v.` #   { 1 ( @ ^ ).A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.+.# f v.A.=.^ a k.A.A.y.>.0 = _ k 8.A.v.e 7 W )   ' O m.A.A.A.A.$.~       ' X o.A.a.b #     } $.A.m.# - q.A.A.A.A.A.>._ $ ..A.A.A.: = ).y.9.0 .   . 9 0.A.A.a.e #     ) ..y.A.A.*.~       } |.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.o.6.o.A.A.v.a.o.A.A.A.A.A.o.9.a.v.A.A.A.l.m.y.a.4.9.v.A.A.A.A.A.A.a.4.4.4.9.v.A.A.A.o.8.4.4.k.A.A.A.6.9.A.A.A.A.A.A.x.a.8.o.A.A.A.a.9.y.A.A.k.4.4.6.m.A.A.A.A.o.8.6.4.0.A.A.A.A.A.a.4.4.4.c.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.",
"A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A.A."
]

## Required for plugins ##
PLUGIN_INFO = PluginInfo(name='albumart', display_name='Album Artwork',
                         desc=_('Download missing album art from amazon.com.'),
                         author='Travis Shirk <travis@pobox.com>',
                         url='http://mesk.nicfit.net/',
                         copyright=\
'''Copyright © 2007 Travis Shirk
Copyright © 2007 Amazon.com''',
                         clazz=AlbumArtPlugin,
                         xpm=XPM)

## For testing ###
if __name__ == '__main__':
    # Search artist (argv[1]) and optional album (argv[2]) and output some data
    import sys
    query = sys.argv[1]
    if len(sys.argv) > 2:
        query += ' ' + sys.argv[2]
    results = amazon.OnDemandAmazonList(amazon.searchByKeyword,
                                        {'keyword': query,
                                         'product_line': 'music'})
    for a in results:
        print '-' * 80
        print "Artist:", a.Artists.Artist
        print "Album Name:", a.ProductName
        print "Release Date:", a.ReleaseDate
        print "Label:", a.Manufacturer
        print "Media:", a.Media
        print "ASIN:", a.Asin
        print "UPC:", a.Upc
        print "URL:", a.URL
        print "Availability:", a.Availability
        print "Price:", a.ListPrice
        print "Used Price:", a.UsedPrice
        print "Third-party New Price:", a.ThirdPartyNewPrice
        print "Cover (small):", a.ImageUrlSmall
        print "Cover (medium):", a.ImageUrlMedium
        print "Cover (large):", a.ImageUrlLarge
        print "Tracks:"
        for t in a.Tracks.Track:
            print '\t%s' % t
        print "All Keys:", dir(a)
