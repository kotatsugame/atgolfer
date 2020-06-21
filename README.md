# AtGolfer

[![Travis.org](https://img.shields.io/travis/kmyk/atgolfer.svg)](https://travis-ci.org/kmyk/atgolfer)
![License](https://img.shields.io/github/license/kmyk/atgolfer.svg)
[![Twitter Follow](https://img.shields.io/twitter/follow/atgolfer1.svg?style=social)](https://twitter.com/intent/follow?screen_name=atgolfer1)

このリポジトリには、AtCoder 上でのコードゴルフの記録更新を報告する Twitter bot [@atgolfer1](https://twitter.com/atgolfer1) のスクリプトが置かれています。

## 動かし方

### とりあえず実行してみる

``` console
$ git clone https://github.com/kmyk/atgolfer

$ cd atgolfer

$ pip3 install beautifulsoup4
$ pip3 install CacheControl
$ pip3 install python-twitter
$ pip3 install requests

$ python3 main.py --verbose --directory=./ --use-atcoder-problems --only-abc00x
[*] load cache from ./shortest_codes.json
[*] load cache from ./latest_submission_ids.json
[*] load cache from ./last_status_id.json
[*] GET https://atcoder.jp/contests/archive?lang=ja
[*] GET https://atcoder.jp/contests/archive?lang=ja&page=1
[*] GET https://kenkoooo.com/atcoder/resources/contests.json
[*] GET https://kenkoooo.com/atcoder/resources/merged-problems.json
[*] 1/36: AtCoder Beginner Contest 001. A. 積雪深差
[*] 2/36: AtCoder Beginner Contest 001. B. 視程の通報
[*] 3/36: AtCoder Beginner Contest 001. C. 風力観測
[*] 4/36: AtCoder Beginner Contest 001. D. 感雨時刻の整理
[*] 5/36: AtCoder Beginner Contest 002. A. 正直者
[*] 6/36: AtCoder Beginner Contest 002. B. 罠
[*] 7/36: AtCoder Beginner Contest 002. C. 直訴
[*] 8/36: AtCoder Beginner Contest 002. D. 派閥
[*] 9/36: AtCoder Beginner Contest 003. A. AtCoder社の給料
...
[*] 33/36: AtCoder Beginner Contest 009. A. 引越し作業
[*] 34/36: AtCoder Beginner Contest 009. B. 心配性な富豪、ファミリーレストランに行く。
[*] 35/36: AtCoder Beginner Contest 009. C. 辞書式順序ふたたび
[*] 36/36: AtCoder Beginner Contest 009. D. 漸化式
[*] store cache to ./shortest_codes.json
[*] store cache to ./latest_submission_ids.json
[*] store cache to ./last_status_id.json
```

### Twitter bot を運用する

Twitter bot [@atgolfer1](https://twitter.com/atgolfer1) を運用するには、bot のための Twitter のアカウントと、5 分おきぐらいにスクリプトを実行してくれるような実行環境が必要です。
具体的には以下が必要となります。

1.  Twitter bot 用のアカウントを作る
1.  Twitter bot を自動で操作するための認証情報を得る
1.  スクリプトを実行するためのサーバを借りる
1.  そのサーバ上でスクリプトが自動実行され Twitter に投稿されるように設定をする

Twitter のアカウントは普通に作って、認証情報はいい感じにしてください。
認証情報をスクリプトに伝えるには環境変数を経由してください。たとえば以下のようにします。

``` console
$ env \
    TWITTER_CONSUMER_KEY=... \
    TWITTER_CONSUMER_SECRET=... \
    TWITTER_ACCESS_TOKEN_KEY=... \
    TWITTER_ACCESS_TOKEN_SECRET=... \
    python3 main.py --post ...
```

サーバについては、性能は求められないのでなんでもいいから VPS (例: [VPS（仮想専用サーバー）｜さくらインターネット](https://vps.sakura.ad.jp/) の一番安いやつやその次に安いやつ) を借り、[crontab](https://ja.wikipedia.org/wiki/Crontab) に以下のような設定をするのがよいでしょう。

``` console
$ crontab -l
#                   m h dom mon dow   command
0,5,10,25,30,35,40,55 *   *   *   *   /usr/bin/env TWITTER_CONSUMER_KEY=... TWITTER_CONSUMER_SECRET=... TWITTER_ACCESS_TOKEN_KEY=... TWITTER_ACCESS_TOKEN_SECRET=... python3 /home/ubuntu/atgolfer/main.py --directory /home/ubuntu/atgolfer --post --use-atcoder-problems
15,45                 *   *   *   *   /usr/bin/env TWITTER_CONSUMER_KEY=... TWITTER_CONSUMER_SECRET=... TWITTER_ACCESS_TOKEN_KEY=... TWITTER_ACCESS_TOKEN_SECRET=... python3 /home/ubuntu/atgolfer/main.py --directory /home/ubuntu/atgolfer --post
```

注意点:

-   いきなり `--post` を付けて実行するとすべての問題についてツイートがされてしまうので、まずは `--post` なしで実行するようにする
-   Twitter bot は何もしていなくても「不審な挙動が……」などとアカウントが凍結されたりしがちなので注意する
-   `TWITTER_ACCESS_TOKEN_SECRET` とかは実質パスワードなので漏らさないように注意する
-   AtCoder から直接スクレイピングすると遅いが、AtCoder Problems を使うとデータの取りこぼしがあるので、両方を使うようにする
-   AtCoder や AtCoder Problems はメンテや負荷などでたまに落ちるので注意する
-   実行が遅くてスクリプトが重複起動してしまうと壊れるので [flock](https://linuxjm.osdn.jp/html/util-linux/man1/flock.1.html) などを活用する
-   データを貯めているファイルに書き込み中にエラーなどで落ちるとデータが消えるので諦めるかコードを修正する
