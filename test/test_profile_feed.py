import unittest
from unittest.mock import Mock, call, patch

from instaloader import InstaloaderContext, Profile
from instaloader.exceptions import BadResponseException, InvalidArgumentException
from instaloader.nodeiterator import NodeIterator


class ProfileFeedTests(unittest.TestCase):
    def make_iterator(self, context, profile_id=123):
        return NodeIterator(context, None, lambda data: data, lambda node: node,
                            profile_feed_id=profile_id)

    def test_pagination_uses_next_max_id(self):
        context = Mock(username='tester')
        context.get_profile_posts.side_effect = [
            {'items': [{'pk': '1'}, {'pk': '2'}],
             'more_available': True, 'next_max_id': 'cursor'},
            {'items': [{'pk': '3'}], 'more_available': False},
        ]
        self.assertEqual(list(self.make_iterator(context)),
                         [{'pk': '1'}, {'pk': '2'}, {'pk': '3'}])
        self.assertEqual(context.get_profile_posts.call_args_list,
                         [call(123, None), call(123, 'cursor')])

    def test_freeze_and_thaw_keep_profile_and_cursor(self):
        context = Mock(username='tester')
        first_page = {'items': [{'pk': '1'}, {'pk': '2'}],
                      'more_available': True, 'next_max_id': 'cursor'}
        context.get_profile_posts.return_value = first_page
        iterator = self.make_iterator(context)
        next(iterator)
        next(iterator)
        frozen = iterator.freeze()
        resumed = self.make_iterator(context)
        resumed.thaw(frozen)
        context.get_profile_posts.return_value = {
            'items': [{'pk': '3'}], 'more_available': False}
        self.assertEqual(list(resumed), [{'pk': '2'}, {'pk': '3'}])
        context.get_profile_posts.assert_called_with(123, 'cursor')
        other = self.make_iterator(context, 456)
        with self.assertRaises(InvalidArgumentException):
            other.thaw(frozen)

    def test_missing_items_is_not_treated_as_empty_profile(self):
        context = Mock(username='tester')
        context.get_profile_posts.return_value = {'status': 'ok'}
        with self.assertRaises(BadResponseException):
            self.make_iterator(context)

    def test_logged_in_profile_uses_feed(self):
        context = Mock(username='tester', is_logged_in=True)
        context.get_profile_posts.return_value = {'items': [], 'more_available': False}
        profile = Profile(context, {'username': 'example', 'id': '123'})
        with patch.object(profile, '_obtain_metadata'):
            self.assertEqual(list(profile.get_posts()), [])
        context.get_profile_posts.assert_called_once_with(123, None)
        context.doc_id_graphql_query.assert_not_called()

    def test_feed_request_parameters(self):
        context = InstaloaderContext(sleep=False, quiet=True)
        try:
            with patch.object(context, 'get_iphone_json', return_value={'items': []}) as request:
                context.get_profile_posts(123, 'cursor')
                request.assert_called_once_with('api/v1/feed/user/123/', {
                    'count': '12', 'include_suggested_users': 'false',
                    'exclude_pinned_posts': 'false', 'max_id': 'cursor',
                })
        finally:
            context.close()


if __name__ == '__main__':
    unittest.main()
