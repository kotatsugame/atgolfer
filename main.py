# Python Version: 3.x
import argparse
import bs4
import datetime
import itertools
import json
import os.path
import requests
import sys
import time
import twitter  # $ sudo pip3 install python-twitter
from collections import namedtuple


Contest = namedtuple('Contest', ['title', 'id'])


def get_html(url):
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.content, 'lxml')
    time.sleep(0.5)
    return soup


def get_json(url):
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    time.sleep(0.5)
    return json.loads(resp.content)


def get_contests(limit=None):
    url = 'https://atcoder.jp/contests/archive?lang=ja'
    finalpage = int(get_html(url).find(
        'ul', class_='pagination').find_all('li')[-1].text)
    contests = []
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
    return contests


# TODO: this function should be a class
# NOTE: this should be a generator because recovering from errors becomes easier
def crawl_contest(contest, shortest_codes, latest_submission_ids):

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
    latest_submission_id = int(submission_trs[0].find_all('td')[4]['data-id'])
    newer_submission_id = int(submission_trs[-1].find_all('td')[4]['data-id'])
    if contest.id in latest_submission_ids:
        if latest_submission_id == latest_submission_ids[contest.id]:
            return  # no new submissions

    # read submissions of tasks
    if (not(contest.id in latest_submission_ids)) or (int(newer_submission_id) > int(latest_submission_ids[contest.id])):
        submission_trs = []
        tasks = soup.find('select', id='select-task').find_all('option')[1:]
        for task in tasks:
            task_id = task['value']
            # NOTE: this query shows submissions with the same length in the ascending order of time
            query = f'f.Language=&f.Status=AC&f.Task={task_id}&f.User=&orderBy=source_length'
            tbody = get_html(f'{url}?{query}').find('tbody')
            if not tbody:
                continue
            submission_trs.append(tbody.find('tr'))

    # check the shortest submissions
    for tr in submission_trs:
        tds = tr.find_all('td')
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
            shortest_codes[task_id] = {}
        text = '\n'.join([f'{contest.title}: {problem_title}',
                          text, f'{url}/{new_submission_id}'])
        yield {'text': text, 'problem_id': task_id}

        # NOTE: update shortest_codes after yielding; this is for cases when it fails to tweet and an exception is thrown
        shortest_codes[task_id]['size'] = new_size
        shortest_codes[task_id]['submission_id'] = new_submission_id
        shortest_codes[task_id]['user'] = new_user

    # NOTE: also this update must be here
    latest_submission_ids[contest.id] = latest_submission_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-atcoder-problems', action='store_true')
    parser.add_argument('--post', action='store_true')
    parser.add_argument('--store')
    parser.add_argument('--load')
    parser.add_argument('--no-store', action='store_const',
                        const=None, dest='store')
    parser.add_argument('--no-load',  action='store_const',
                        const=None, dest='load')
    parser.add_argument('--consumer-key')
    parser.add_argument('--consumer-secret')
    parser.add_argument('--access-token-key')
    parser.add_argument('--access-token-secret')
    parser.add_argument('--only-abc00x', action='store_true', help='for debug')
    args = parser.parse_args()

    # logging in is postponed
    if args.post:
        if not args.consumer_key or not args.consumer_secret or not args.access_token_key or not args.access_token_secret:
            parser.error(
                'all of --{consumer,access-token}-{key,secret} are required if --post is used')
        api = None

    # load cache
    shortest_codes = {}
    latest_submission_ids = {}
    last_status_id = {}
    if args.load is not None and os.path.exists(args.load):
        print('[*] load cache from', args.store, file=sys.stderr)
        with open(args.load) as fh:
            loaded_cache = json.load(fh)
        shortest_codes = loaded_cache['shortest_codes']
        latest_submission_ids = loaded_cache['latest_submission_ids']
        last_status_id = loaded_cache['last_status_id']

    # get data from AtCoder
    def read_atcoder(limit=None):
        contests = get_contests(limit=limit)
        if args.only_abc00x:
            contests = [
                contest for contest in contests if contest.id.startswith('abc00')]
        if limit is None:
            # NOTE: add poison for stability
            contests = [Contest('practice contest', 'practice')] + contests
        contest_count = len(contests)

        for i, contest in enumerate(contests):
            print(
                '[*]', f'{i + 1}/{contest_count}: {contest.title}', file=sys.stderr)
            for data in crawl_contest(contest, shortest_codes=shortest_codes, latest_submission_ids=latest_submission_ids):
                yield data

    # get data from AtCoder Problems
    def read_atcoder_problems():
        contests = get_json(
            'https://kenkoooo.com/atcoder/atcoder-api/info/contests')
        merged_problems = get_json(
            'https://kenkoooo.com/atcoder/atcoder-api/info/merged-problems')
        if args.only_abc00x:
            contests = [
                contest for contest in contests if contest['id'].startswith('abc00')]
            merged_problems = [
                problem for problem in merged_problems if problem.get('shortest_contest_id', '').startswith('abc00')]

        contests_dict = {contest['id']: contest for contest in contests}
        crawled_contest_ids = set()
        for i, problem in enumerate(merged_problems):
            if 'shortest_submission_id' not in problem:
                continue
            contest_id = problem['shortest_contest_id']
            contest = Contest(contests_dict[contest_id]['title'], contest_id)
            print(
                '[*]', f'{i + 1}/{len(merged_problems)}: {contest.title}. {problem["title"]}', file=sys.stderr)

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

    # get data
    try:
        if args.use_atcoder_problems:
            gen = itertools.chain(read_atcoder(limit=5),
                                  read_atcoder_problems())
        else:
            gen = read_atcoder()
        for data in gen:
            in_reply_to_status_id = last_status_id.get(data['problem_id'])

            print('[*]', data['text'], file=sys.stderr)
            if in_reply_to_status_id is not None:
                print('[*] in_reply_to_status_id =',
                      in_reply_to_status_id, file=sys.stderr)

            # post
            if args.post:
                if api is None:
                    api = twitter.Api(
                        consumer_key=args.consumer_key,
                        consumer_secret=args.consumer_secret,
                        access_token_key=args.access_token_key,
                        access_token_secret=args.access_token_secret,
                        sleep_on_rate_limit=True)
                status = api.PostUpdate(
                    data['text'], in_reply_to_status_id=in_reply_to_status_id)
                last_status_id[data['problem_id']] = status.id
                time.sleep(3)

    finally:
        # write cache
        if args.store is not None:
            print('[*] store cache to', args.store, file=sys.stderr)
            dirname = os.path.dirname(args.store)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname)
            stored_cache = {
                'shortest_codes': shortest_codes,
                'latest_submission_ids': latest_submission_ids,
                'last_status_id': last_status_id,
            }
            with open(args.store, 'w') as fh:
                json.dump(stored_cache, fh)


if __name__ == '__main__':
    main()
