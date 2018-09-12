# Python Version: 3.x
import argparse
import bs4
import datetime
import json
import os.path
import requests
import sys
import time
import twitter  # $ sudo pip3 install python-twitter


def get_contests():
    url = 'https://kenkoooo.com/atcoder/atcoder-api/info/contests'
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    return json.loads(resp.content)


def get_merged_problems():
    url = 'https://kenkoooo.com/atcoder/atcoder-api/info/merged-problems'
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    return json.loads(resp.content)


def get_submission(url):
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.content, 'lxml')

    data = {}
    data['url'] = url

    id_, = soup.findAll('span', class_='h2')
    assert id_.text.startswith('Submission #')
    data['id'] = id_.text.partition('#')[2]

    source_code = soup.find(id='submission-code')
    data['souce_code'] = source_code.text

    submission_info, test_cases_summary, test_cases_data = soup.findAll('table')

    data['info'] = {}
    for tr in submission_info.findAll('tr'):
        th = tr.find('th')
        td = tr.find('td')
        key = th.text.replace(' ', '_').lower()
        value = td.text.strip()
        data['info'][key] = value

    data['test_cases'] = []
    for tr in test_cases_data.find('tbody').findAll('tr'):
        td = tr.findAll('td')
        data['test_cases'] += [ {
            'case_name': td[0].text,
            'status':    td[1].text,
            'exec_time': td[2].text,
            'memory':    td[3].text,
        } ]

    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--post', action='store_true')
    parser.add_argument('--store')
    parser.add_argument('--load')
    parser.add_argument('--no-store', action='store_const', const=None, dest='store')
    parser.add_argument('--no-load',  action='store_const', const=None, dest='load')
    parser.add_argument('--consumer-key')
    parser.add_argument('--consumer-secret')
    parser.add_argument('--access-token-key')
    parser.add_argument('--access-token-secret')
    args = parser.parse_args()

    # logging in is postponed
    if args.post:
        if not args.consumer_key or not args.consumer_secret or not args.access_token_key or not args.access_token_secret:
            parser.error('all of --{consumer,access-token}-{key,secret} are required if --post is used')
        api = None

    # load cache
    last_merged_problems = {}
    if args.load is not None and os.path.exists(args.load):
        with open(args.load) as fh:
            last_merged_problems = json.load(fh)

    # get data
    contests = get_contests()
    merged_problems = get_merged_problems()
    content_from_id = { row['id']: row for row in contests }

    # write cache
    if args.store is not None:
        dirname = os.path.dirname(args.store)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(args.store, 'w') as fh:
            json.dump(merged_problems, fh)

    # enumerate golfed submissions
    last_problem_from_id = { row['id']: row for row in last_merged_problems }
    for problem in merged_problems:
        if problem['solver_count'] == 0:
            continue
        last_problem = last_problem_from_id.get(problem['id'], {})
        last_submission_id = last_problem.get('shortest_submission_id')
        if problem['shortest_submission_id'] == last_submission_id:
            continue

        # get submission
        url = 'https://beta.atcoder.jp/contests/{shortest_contest_id}/submissions/{shortest_submission_id}'.format(**problem)
        new_submission = get_submission(url)

        contest_title = content_from_id[problem['shortest_contest_id']]['title']
        problem_title = problem['title']
        new_user = problem['shortest_user_id']
        new_size = new_submission['info']['code_size']
        if last_submission_id:
            old_url = 'https://beta.atcoder.jp/contests/{shortest_contest_id}/submissions/{shortest_submission_id}'.format(**last_problem)
            old_submission = get_submission(old_url)
            old_user = last_problem['shortest_user_id']
            old_size = old_submission['info']['code_size']
            if new_user == old_user:
                text = f'{new_user} さんが自身のショートコードを更新しました！ ({old_size} → {new_size})'
            else:
                text = f'{new_user} さんが {old_user} さんからショートコードを奪取しました！ ({old_size} → {new_size})'
        else:
            text = f'{new_user} さんがショートコードを打ち立てました！ ({new_size})'
        text = '\n'.join([ f'{contest_title}: {problem_title}', text, url ])
        print('[*]', text, file=sys.stderr)

        # post
        if args.post:
            if api is None:
                api = twitter.Api(
                    consumer_key=args.consumer_key,
                    consumer_secret=args.consumer_secret,
                    access_token_key=args.access_token_key,
                    access_token_secret=args.access_token_secret,
                    sleep_on_rate_limit=True)
            api.PostUpdate(text)

        # wait
        time.sleep(3)


if __name__ == '__main__':
    main()
