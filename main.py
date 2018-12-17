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
from collections import namedtuple


def get_contests():
    url = 'https://beta.atcoder.jp/contests/archive?lang=ja'
    print('[*] GET', url, file=sys.stderr)
    resp = requests.get(url)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.content, 'lxml')
    time.sleep(1)
    
    finalpage = int(soup.find('ul', class_='pagination pagination-sm mt-0 mb-1').find_all('li')[-1].text)
    contests = []
    Contest = namedtuple('Contest', [ 'title', 'path' ])
    for i in range(1, finalpage+1):
        print('[*] GET', f'{url}&page={i}', file=sys.stderr)
        resp = requests.get(f'{url}&page={i}')
        resp.raise_for_status()
        tbody = bs4.BeautifulSoup(resp.content, 'lxml').find('tbody')
        
        for tr in tbody.find_all('tr'):
            a = tr.find_all('a')[1]
            contests.append(Contest(title=a.text, path=a['href']))
        time.sleep(1)
    return contests


def can_read_submissions(contest_beta_path):
    resp = requests.get(f'https://beta.atcoder.jp{contest_beta_path}')
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.content, 'lxml')
    tabs = soup.find('ul', class_='nav nav-tabs').find_all('li')
    for tab in tabs:
        ul = tab.find('ul')
        if not ul: continue
        li = ul.find('li')
        if not li: continue
        if li.find('a', href=f'{contest_beta_path}/submissions'):
            return True
    return False


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
    shortest_codes = {}
    latest_submission_ids = {}
    if args.load is not None and os.path.exists(args.load):
        with open(args.load) as fh:
            shortest_codes, latest_submission_ids = json.load(fh)

    # get data
    contests = get_contests()
    contest_count = len(contests)
    contest_number = 0
    for contest in contests:
        contest_title = contest.title
        contest_beta_path = contest.path
        contest_number += 1
        print('[*]', f'{contest_number}/{contest_count}: {contest_title}', file=sys.stderr)
        if not can_read_submissions(contest_beta_path): continue
        
        url = f'https://beta.atcoder.jp{contest_beta_path}/submissions'
        resp = requests.get(url)
        resp.raise_for_status()
        soup = bs4.BeautifulSoup(resp.content, 'lxml')
        
        tbody = soup.find('tbody')
        if not tbody: continue
        tr = tbody.find('tr')
        latest_submission_id = tr.find_all('td')[4]['data-id']
        if contest_beta_path in latest_submission_ids:
            if latest_submission_id == latest_submission_ids[contest_beta_path]:
                continue
        latest_submission_ids[contest_beta_path] = latest_submission_id
        
        tasks = soup.find('select', id='select-task').find_all('option')[1:]
        for task in tasks:
            task_id = task['value']
            resp = requests.get(f'{url}?f.Language=&f.Status=AC&f.Task={task_id}&f.User=&orderBy=source_length')  # NOTE: this query shows submissions with the same length in the ascending order of time
            resp.raise_for_status()
            soup = bs4.BeautifulSoup(resp.content, 'lxml')
            tbody = soup.find('tbody')
            if not tbody: continue
            tds = tbody.find('tr').find_all('td')
            problem_title = tds[1].find('a').text
            new_user = tds[2].find('a')['href'].split('/')[2]
            new_submission_id = tds[4]['data-id']
            new_size = int(tds[5].text.split(' ')[0])
            if task_id in shortest_codes:
                old_size = shortest_codes[task_id]['size']
                old_submission_id = shortest_codes[task_id]['submission_id']
                old_user = shortest_codes[task_id]['user']
                if new_size < old_size or (new_size == old_size and new_submission_id < old_submission_id):
                    if new_user == old_user:
                        text = f'{new_user} さんが自身のショートコードを更新しました！ ({old_size} Byte → {new_size} Byte)'
                    else:
                        text = f'{new_user} さんが {old_user} さんからショートコードを奪取しました！ ({old_size} Byte → {new_size} Byte)'
                else: continue
            else:
                text = f'{new_user} さんがショートコードを打ち立てました！ ({new_size} Byte)'
                shortest_codes[task_id] = {}
            shortest_codes[task_id]['size'] = new_size
            shortest_codes[task_id]['submission_id'] = new_submission_id
            shortest_codes[task_id]['user'] = new_user
            text = '\n'.join([ f'{contest_title}: {problem_title}', text, url+'/'+new_submission_id ])
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
    
    # write cache
    if args.store is not None:
        dirname = os.path.dirname(args.store)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(args.store, 'w') as fh:
            json.dump([ shortest_codes, latest_submission_ids ], fh)


if __name__ == '__main__':
    main()
