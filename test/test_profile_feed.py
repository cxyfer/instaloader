import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from instaloader import Profile
from instaloader.exceptions import BadResponseException, InvalidArgumentException
from instaloader.nodeiterator import FrozenNodeIterator


class ProfilePostsTests(unittest.TestCase):
    def make_media(self, pk, media_type=1):
        return {
            'pk': str(pk), 'code': 'code{}'.format(pk), 'media_type': media_type,
            'taken_at': 1700000000 + pk, 'caption': None, 'has_liked': False,
            'like_count': 0, 'comment_count': 0,
            'image_versions2': {'candidates': [{'url': 'https://example.com/image.jpg'}]},
            'user': {'pk': '123', 'username': 'example', 'is_private': False,
                     'full_name': '', 'profile_pic_url': 'https://example.com/avatar.jpg'},
        }

    def page(self, ids=(), cursor=None):
        return {'data': {'xdt_api__v1__feed__user_timeline_graphql_connection': {
            'edges': [{'node': self.make_media(pk)} for pk in ids],
            'page_info': {'has_next_page': cursor is not None, 'end_cursor': cursor},
        }}}

    def make_profile(self, context, username='example'):
        profile = Profile(context, {'username': username, 'id': '123'})
        profile._has_full_metadata = True
        return profile

    def test_logged_in_profile_uses_web_graphql_even_without_iphone_support(self):
        for iphone_support in (True, False):
            with self.subTest(iphone_support=iphone_support):
                context = Mock(username='tester', is_logged_in=True, iphone_support=iphone_support)
                context.doc_id_graphql_query.return_value = self.page()
                self.assertEqual(list(self.make_profile(context).get_posts()), [])
                request = context.doc_id_graphql_query.call_args
                self.assertEqual(request.args[0], '28542612348729311')
                self.assertEqual(request.args[1]['username'], 'example')
                self.assertEqual(request.args[1]['first'], 12)
                self.assertIsNone(request.args[1]['after'])
                self.assertEqual(request.args[2], 'https://www.instagram.com/example/')
                context.get_iphone_json.assert_not_called()

    def test_pagination_uses_connection_query_and_end_cursor(self):
        context = Mock(username='tester', is_logged_in=True)
        context.doc_id_graphql_query.side_effect = [self.page((1, 2), 'cursor'), self.page((3,))]
        self.assertEqual([post.mediaid for post in self.make_profile(context).get_posts()], [1, 2, 3])
        requests = context.doc_id_graphql_query.call_args_list
        self.assertEqual([request.args[0] for request in requests],
                         ['28542612348729311', '28142289515441884'])
        self.assertEqual(requests[1].args[1]['after'], 'cursor')
        self.assertEqual(requests[1].args[1]['first'], 12)
        self.assertFalse(requests[1].args[1]['include_multi_captions'])
        context.get_iphone_json.assert_not_called()

    def test_freeze_and_thaw_keep_profile_and_cursor(self):
        context = Mock(username='tester', is_logged_in=True)
        context.doc_id_graphql_query.return_value = self.page((1, 2), 'cursor')
        iterator = self.make_profile(context).get_posts()
        next(iterator)
        next(iterator)
        frozen = FrozenNodeIterator(**iterator.freeze()._asdict())
        resumed = self.make_profile(context).get_posts()
        resumed.thaw(frozen)
        context.doc_id_graphql_query.return_value = self.page((3,))
        self.assertEqual([post.mediaid for post in resumed], [2, 3])
        self.assertEqual(context.doc_id_graphql_query.call_args.args[0], '28142289515441884')
        self.assertEqual(context.doc_id_graphql_query.call_args.args[1]['after'], 'cursor')
        other = self.make_profile(context, 'other').get_posts()
        self.assertNotEqual(iterator.magic, other.magic)
        with self.assertRaises(InvalidArgumentException):
            other.thaw(frozen)

    def test_invalid_first_page_is_not_treated_as_empty_profile(self):
        responses = ({'data': None}, {'data': {}},
                     {'data': {'xdt_api__v1__feed__user_timeline_graphql_connection': {}}})
        for response in responses:
            with self.subTest(response=response):
                context = Mock(username='tester', is_logged_in=True)
                context.doc_id_graphql_query.return_value = response
                with self.assertRaises(BadResponseException):
                    self.make_profile(context).get_posts()

    def test_invalid_pagination_response_is_not_treated_as_end_of_profile(self):
        context = Mock(username='tester', is_logged_in=True)
        context.doc_id_graphql_query.side_effect = [self.page((1,), 'cursor'), {'data': {}}]
        iterator = self.make_profile(context).get_posts()
        next(iterator)
        with self.assertRaises(BadResponseException):
            next(iterator)

    def test_web_media_preserves_download_fields_and_sidecar_ids(self):
        for iphone_support in (True, False):
            with self.subTest(iphone_support=iphone_support):
                context = Mock(username='tester', is_logged_in=True, iphone_support=iphone_support)
                media = self.make_media(1, 8)
                media['carousel_media'] = [self.make_media(2), self.make_media(3, 2)]
                media['carousel_media'][1]['video_versions'] = [{'url': 'https://example.com/video.mp4'}]
                response = self.page()
                response['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['edges'] = [{'node': media}]
                context.doc_id_graphql_query.return_value = response
                post = next(self.make_profile(context).get_posts())
                self.assertEqual(post.owner_id, 123)
                self.assertEqual(post.date_utc, datetime.utcfromtimestamp(media['taken_at']))
                self.assertEqual(post.typename, 'GraphSidecar')
                children = list(post.get_sidecar_nodes())
                self.assertEqual([child.id for child in children], ['2', '3'])
                self.assertEqual([child.is_video for child in children], [False, True])
                self.assertEqual(children[1].video_url, 'https://example.com/video.mp4')
                context.get_iphone_json.assert_not_called()

    def test_logged_out_profile_keeps_legacy_graphql_iterator(self):
        context = Mock(username=None, is_logged_in=False)
        profile = Profile(context, {'username': 'example', 'id': '123',
                                    'edge_owner_to_timeline_media': {
                                        'edges': [], 'page_info': {'has_next_page': False}}})
        with patch.object(profile, '_obtain_metadata'):
            iterator = profile.get_posts()
        self.assertEqual(list(iterator), [])
        self.assertEqual(iterator.freeze().doc_id, '7950326061742207')
        context.doc_id_graphql_query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
