import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from rss_data_service import Catalogue


class RSSDataTest(unittest.TestCase):
    def test_standard_rss_has_stable_unique_articles_and_long_readable_content(self):
        catalogue=Catalogue('http://127.0.0.1:18491')
        payload=catalogue.feed(1);root=ET.fromstring(payload)
        self.assertLess(len(payload),5*1024*1024)
        items=root.findall('./channel/item');self.assertEqual(len(items),100)
        self.assertEqual(len({item.findtext('guid') for item in items}),100)
        self.assertEqual(items[0].findtext('title'),'Journal 1 article 1')
        self.assertGreaterEqual(len(items[0].findtext('description').encode()),32768)
        self.assertEqual(payload,catalogue.feed(1))

    def test_opml_links_each_normal_feed_and_article_routes_match_content(self):
        catalogue=Catalogue('http://127.0.0.1:18491')
        outlines=ET.fromstring(catalogue.opml()).findall('./body/outline')
        self.assertEqual(len(outlines),10)
        self.assertEqual(outlines[-1].attrib['xmlUrl'],'http://127.0.0.1:18491/feeds/10.xml')
        self.assertEqual(catalogue.response('/articles/1/1.html')[1],catalogue.body.encode())

    def test_unknown_or_out_of_range_paths_are_not_hidden_status_endpoints(self):
        catalogue=Catalogue('http://127.0.0.1:18491')
        for path in ['/status','/oracle','/feeds/11.xml','/articles/1/101.html']:
            with self.subTest(path=path),self.assertRaises(KeyError):catalogue.response(path)


if __name__=='__main__':unittest.main()
