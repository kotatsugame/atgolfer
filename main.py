# Python Version: 3.x
import argparse
import datetime
import dotenv
import itertools
import json
import os
import sys
import time
from logging import DEBUG, WARNING, StreamHandler, getLogger
from typing import *

import bs4
import cachecontrol
import cachecontrol.caches.file_cache
import requests
import twitter
import pytwitter


# ID/PASS
dotenv.load_dotenv()
TWITTER_CONSUMER_KEY = os.getenv('TWITTER_CONSUMER_KEY')
TWITTER_CONSUMER_SECRET = os.getenv('TWITTER_CONSUMER_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')
ATCODER_ID = os.getenv('ATCODER_ID')
ATCODER_PASSWORD = os.getenv('ATCODER_PASSWORD')


# contest class
class Contest(NamedTuple):
    title: str
    id: str


# logging
logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
logger.setLevel(DEBUG)
logger.addHandler(handler)
logger.propagate = False


# requests
sess = requests.Session()
NUM_RETRIES = 3 # number of retries


# hidden contests
# list : https://github.com/kenkoooo/AtCoderProblems/blob/master/atcoder-problems-frontend/public/static_data/backend/hidden_contests.json
# update at : 2021/04/29
hidden_contests = ['ukuku09', 'summerfes2018-div1', 'summerfes2018-div2', 'monamieHB2021', 'tkppc6-1', 'genocon2021']


def get_html(url: str) -> bs4.BeautifulSoup:
    logger.debug('[*] GET %s', url)
    resp = sess.get(url)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.content, 'lxml')
    time.sleep(1)
    return soup


def get_json(url: str) -> Any:
    logger.debug(f'[*] GET %s', url)
    resp = sess.get(url)
    resp.raise_for_status()
    time.sleep(1)
    return json.loads(resp.content)


def get_contests(limit: Optional[int] = None) -> List[Contest]:
    contests = []

    # archived contests
    url = 'https://atcoder.jp/contests/archive?lang=ja'
    finalpage = int(get_html(url).find('ul', class_='pagination').find_all('li')[-1].text)
    for i in range(1, finalpage + 1):
        tbody = get_html(f'{url}&page={i}').find('tbody')
        for tr in tbody.find_all('tr'):
            a = tr.find_all('a')[1]
            contest_path = a['href']
            assert contest_path.startswith('/contests/')
            contest_id = contest_path[len('/contests/'):]
            contests.append(Contest(title=a.text, id=contest_id))
            if limit is not None and len(contests) >= limit:
                return contests

    # permanent contests
    tbody = get_html('https://atcoder.jp/contests/?lang=ja').find('div', id='contest-table-permanent').find('tbody')
    for tr in tbody.find_all('tr'):
        a = tr.find('a')
        contest_path = a['href']
        assert contest_path.startswith('/contests/')
        contest_id = contest_path[len('/contests/'):]
        contests.append(Contest(title=a.text, id=contest_id))
        if limit is not None and len(contests) >= limit:
            return contests

    # hidden contests
    for contest_id in hidden_contests:
        contest_title = get_html(f'https://atcoder.jp/contests/{contest_id}').find('h1').text
        contests.append(Contest(title=contest_title, id=contest_id))
        if limit is not None and len(contests) >= limit:
            return contests

    return contests


# TODO: this function should be a class
# NOTE: this should be a generator because recovering from errors becomes easier
def crawl_contest(contest: Contest, shortest_codes: Dict[str, Dict[str, Any]], latest_submission_ids: Dict[str, int]) -> Iterator[Dict[str, str]]:

    # read /contests/{contest_id}/submissions to list tasks and check new submissions
    try:
        url = f'https://atcoder.jp/contests/{contest.id}/submissions'
        soup = get_html(url)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # TODO: when is this line executed?
            return  # no privilege to read
        else:
            raise e
    tbody = soup.find('tbody')
    assert tbody
    submission_trs = tbody.find_all('tr')

    offset = 0
    try:
        latest_submission_id = int(submission_trs[0].find_all('td')[offset + 4]['data-id'])
    except KeyError:
        # using account has administrative rights to this contest
        offset = 1
        latest_submission_id = int(submission_trs[0].find_all('td')[offset + 4]['data-id'])

    newer_submission_id = int(submission_trs[-1].find_all('td')[offset + 4]['data-id'])
    if contest.id in latest_submission_ids:
        if latest_submission_id == latest_submission_ids[contest.id]:
            return  # no new submissions

    # read submissions of tasks
    success_to_read = True
    if (not (contest.id in latest_submission_ids)) or (int(newer_submission_id) > int(latest_submission_ids[contest.id])):
        submission_trs = []
        tasks = soup.find('select', id='select-task').find_all('option')[1:]
        for task in tasks:
            task_id = task['value']
            for _ in range(NUM_RETRIES):
                try:
                    # NOTE: this query shows submissions with the same length in the ascending order of time
                    query = f'f.Language=&f.Status=AC&f.Task={task_id}&f.User=&orderBy=source_length'
                    soup = get_html(f'{url}?{query}')
                    if soup is not None:
                        break
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 500:
                        # orderBy=source_length is too heavy
                        time.sleep(5)
                    else:
                        raise e
            else:
                logger.error(f'[*] failed to read from {contest.id}/{task_id}')
                success_to_read = False
                continue
            tbody = soup.find('tbody')
            if not tbody:
                continue
            submission_trs.append(tbody.find('tr'))

    # check the shortest submissions
    for tr in submission_trs:
        tds = tr.find_all('td')[offset:]
        if tds[6].find('span').text != 'AC':
            continue
        problem_title = tds[1].find('a').text
        task_id = tds[1].find('a')['href'].split('/')[-1]
        new_user = tds[2].find('a')['href'].split('/')[-1]
        new_submission_id = int(tds[4]['data-id'])
        new_size = int(tds[5].text.split(' ')[0])
        if task_id in shortest_codes:
            old_size = shortest_codes[task_id]['size']
            old_submission_id = int(shortest_codes[task_id]['submission_id'])
            old_user = shortest_codes[task_id]['user']
            if new_size < old_size or (new_size == old_size and new_submission_id < old_submission_id):
                if new_user == old_user:
                    text = f'{new_user} さんが自身のショートコードを更新しました！ ({old_size} Byte → {new_size} Byte)'
                else:
                    text = f'{new_user} さんが {old_user} さんからショートコードを奪取しました！ ({old_size} Byte → {new_size} Byte)'
            else:
                continue
        else:
            text = f'{new_user} さんがショートコードを打ち立てました！ ({new_size} Byte)'
        text = '\n'.join([f'{contest.title}: {problem_title}', text, f'{url}/{new_submission_id}'])
        yield {'text': text, 'problem_id': task_id}

        # NOTE: update shortest_codes after yielding; this is for cases when it fails to tweet and an exception is thrown
        if task_id not in shortest_codes:
            shortest_codes[task_id] = {}
        shortest_codes[task_id]['size'] = new_size
        shortest_codes[task_id]['submission_id'] = new_submission_id
        shortest_codes[task_id]['user'] = new_user

    # NOTE: also this update must be here
    if success_to_read:
        latest_submission_ids[contest.id] = latest_submission_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-atcoder-problems', action='store_true')
    parser.add_argument('-d', '--directory', default=os.environ.get('ATGOLFER_DIR'))
    parser.add_argument('-n', '--dry-run', action='store_true')
    parser.add_argument('--post', action='store_true')
    parser.add_argument('--only-abc00x', action='store_true', help='for debug')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    if not args.verbose:
        logger.setLevel(WARNING)

    if args.directory is None:
        parser.error('the following arguments are required: --directory')

    # logging in to twitter is postponed
    if args.post:
        assert TWITTER_CONSUMER_KEY is not None
        assert TWITTER_CONSUMER_SECRET is not None
        assert TWITTER_ACCESS_TOKEN is not None
        assert TWITTER_ACCESS_SECRET is not None
        api = None

    # set web cache
    global sess
    web_cache_path = os.path.join(args.directory, 'web_cache')
    web_cache = cachecontrol.caches.file_cache.FileCache(web_cache_path, forever=True)
    sess = cachecontrol.CacheControl(sess, cache=web_cache)

    # login
    assert ATCODER_ID is not None
    assert ATCODER_PASSWORD is not None
    csrf_token = get_html('https://atcoder.jp/login').find(name='input', attrs={'name': 'csrf_token'})['value']
    logger.info('[*] log in to atcoder')
    resp = sess.post('https://atcoder.jp/login', {'username': ATCODER_ID, 'password': ATCODER_PASSWORD, 'csrf_token': csrf_token})
    logger.debug('[*] login info : %s', str(resp))

    # load cache
    shortest_codes: Dict[str, Dict[str, Any]] = {}
    latest_submission_ids: Dict[str, int] = {}
    last_status_id: Dict[str, int] = {}
    shortest_codes_json_path = os.path.join(args.directory, 'shortest_codes.json')
    latest_submission_ids_json_path = os.path.join(args.directory, 'latest_submission_ids.json')
    last_status_id_json_path = os.path.join(args.directory, 'last_status_id.json')
    if os.path.exists(shortest_codes_json_path):
        logger.debug('[*] load cache from %s', shortest_codes_json_path)
        with open(shortest_codes_json_path) as fh:
            shortest_codes = json.load(fh)
    if os.path.exists(latest_submission_ids_json_path):
        logger.debug('[*] load cache from %s', latest_submission_ids_json_path)
        with open(latest_submission_ids_json_path) as fh:
            latest_submission_ids = json.load(fh)
    if os.path.exists(last_status_id_json_path):
        logger.debug('[*] load cache from %s', last_status_id_json_path)
        with open(last_status_id_json_path) as fh:
            last_status_id = json.load(fh)

    # get data from AtCoder
    def read_atcoder(limit: Optional[int] = None) -> Iterator[Dict[str, str]]:
        contests = get_contests(limit=limit)
        if args.only_abc00x:
            contests = [contest for contest in contests if contest.id.startswith('abc00')]
        if limit is None:
            # NOTE: add poison for stability
            contests = [Contest('practice contest', 'practice')] + contests
        contest_count = len(contests)

        for i, contest in enumerate(contests):
            logger.debug(f'[*] {i + 1}/{contest_count}: {contest.title}')
            for data in crawl_contest(contest, shortest_codes=shortest_codes, latest_submission_ids=latest_submission_ids):
                yield data

    # get data from AtCoder Problems
    def read_atcoder_problems() -> Iterator[Dict[str, str]]:
        contests: List[Dict[str, Any]] = get_json('https://kenkoooo.com/atcoder/resources/contests.json')
        merged_problems: List[Dict[str, Any]] = get_json('https://kenkoooo.com/atcoder/resources/merged-problems.json')
        if args.only_abc00x:
            contests = [contest for contest in contests if contest['id'].startswith('abc00')]
            merged_problems = [problem for problem in merged_problems if (problem['shortest_contest_id'] or '').startswith('abc00')]

        contests_dict = {contest['id']: contest for contest in contests}
        crawled_contest_ids: Set[str] = set()
        for i, problem in enumerate(merged_problems):
            if problem['shortest_submission_id'] is None:
                continue
            contest_id = problem['shortest_contest_id']
            contest = Contest(contests_dict[contest_id]['title'], contest_id)
            logger.debug(f'[*] {i + 1}/{len(merged_problems)}: {contest.title}. {problem["title"]}')

            if problem['id'] in shortest_codes:
                if problem['shortest_submission_id'] == shortest_codes[problem['id']]['submission_id']:
                    continue
            if contest.id in latest_submission_ids:
                if problem['shortest_submission_id'] < latest_submission_ids[contest.id]:
                    continue

            if contest.id not in crawled_contest_ids:
                crawled_contest_ids.add(contest.id)
                for data in crawl_contest(contest, shortest_codes=shortest_codes, latest_submission_ids=latest_submission_ids):
                    yield data

    def post_text(text: str, in_reply_to_status_id: Optional[int] = None):
        nonlocal api
        logger.info('[*] post:\n%s', text)
        exclude_reply_user_ids = None
        if twitter.twitter_utils.calc_expected_status_length(text) > twitter.api.CHARACTER_LIMIT:
            a = text[:len(text) * 2 // 5]
            b = text[len(text) // 2:]
            while twitter.twitter_utils.calc_expected_status_length(a + ' (省略) ' + b) > twitter.api.CHARACTER_LIMIT:
                a = a[:len(a) * 4 // 5]
                b = a[len(a) // 5:]
            text = a + ' (省略) ' + b
            logger.info('[*] post:\n%s', text)
        if in_reply_to_status_id is not None:
            logger.debug('[*] in_reply_to_status_id = %s', in_reply_to_status_id)
            in_reply_to_status_id = str(in_reply_to_status_id)
            exclude_reply_user_ids = []
        if args.dry_run or not args.post:
            logger.info('[*] ignored.')
            return
        if api is None:
            api = pytwitter.Api(consumer_key=TWITTER_CONSUMER_KEY, consumer_secret=TWITTER_CONSUMER_SECRET, access_token=TWITTER_ACCESS_TOKEN, access_secret=TWITTER_ACCESS_SECRET, sleep_on_rate_limit=True)
        status = api.create_tweet(text=text, reply_exclude_reply_user_ids=exclude_reply_user_ids, reply_in_reply_to_tweet_id=in_reply_to_status_id)
        last_status_id[data['problem_id']] = int(status.id)
        logger.info('[*] done: https://twitter.com/-/status/%s', status.id)
        logger.debug('[*] sleep 60 seconds...')
        time.sleep(60)

    # get data
    try:
        if args.use_atcoder_problems:
            gen: Iterator[Dict[str, str]] = itertools.chain(read_atcoder(limit=5), read_atcoder_problems())
        else:
            gen = read_atcoder()
        for data in gen:
            post_text(data['text'], in_reply_to_status_id=last_status_id.get(data['problem_id']))

    except Exception as e:
        assert not isinstance(e, KeyboardInterrupt)
        # post_text(e.__class__.__name__)
        raise e

    finally:
        # write cache
        if not args.dry_run:
            if not os.path.exists(args.directory):
                os.makedirs(args.directory)
            logger.debug('[*] store cache to %s', shortest_codes_json_path)
            with open(shortest_codes_json_path, 'w') as fh:
                json.dump(shortest_codes, fh)
            logger.debug('[*] store cache to %s', latest_submission_ids_json_path)
            with open(latest_submission_ids_json_path, 'w') as fh:
                json.dump(latest_submission_ids, fh)
            logger.debug('[*] store cache to %s', last_status_id_json_path)
            with open(last_status_id_json_path, 'w') as fh:
                json.dump(last_status_id, fh)


if __name__ == '__main__':
    main()
