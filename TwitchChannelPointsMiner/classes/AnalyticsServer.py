import json
import logging
import os
from datetime import datetime
from pathlib import Path
from threading import Thread

from flask import Flask, Response, cli, render_template, request

from TwitchChannelPointsMiner.classes.Settings import Settings

cli.show_server_banner = lambda *_: None
logger = logging.getLogger(__name__)


def streamers_available():
    path = Settings.analytics_path
    return [
        f
        for f in os.listdir(path)
        if os.path.isfile(os.path.join(path, f)) and f.endswith(".json")
    ]


def filter_datas(start_date, end_date, datas):
    # Note: https://stackoverflow.com/questions/4676195/why-do-i-need-to-multiply-unix-timestamps-by-1000-in-javascript
    start_date = (
        datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000
        if start_date is not None
        else 0
    )
    end_date = (
        datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000
        if end_date is not None
        else datetime.now().timestamp() * 1000
    )

    datas["series"] = (
        [d for d in datas["series"] if start_date <= d["x"] <= end_date]
        if "series" in datas
        else []
    )
    datas["annotations"] = (
        [d for d in datas["annotations"] if start_date <= d["x"] <= end_date]
        if "annotations" in datas
        else []
    )

    return datas


def read_json(streamer, return_response=True):
    start_date = request.args.get("startDate", type=str)
    end_date = request.args.get("endDate", type=str)

    path = Settings.analytics_path
    streamer = streamer if streamer.endswith(".json") else f"{streamer}.json"
    if return_response is True:
        return Response(
            json.dumps(
                filter_datas(
                    start_date, end_date, json.load(open(os.path.join(path, streamer)))
                )
            )
            if streamer in streamers_available()
            else [],
            status=200,
            mimetype="application/json",
        )
    return (
        json.load(open(os.path.join(path, streamer)))
        if streamer in streamers_available()
        else []
    )


def get_challenge_points(streamer):
    datas = read_json(streamer, return_response=False)
    if datas != {}:
        return datas["series"][-1]["y"]
    return 0


def json_all():
    return Response(
        json.dumps(
            [
                {
                    "name": streamer.strip(".json"),
                    "data": read_json(streamer, return_response=False),
                }
                for streamer in streamers_available()
            ]
        ),
        status=200,
        mimetype="application/json",
    )


def index(refresh=5, days_ago=7):
    return render_template(
        "charts.html",
        refresh=(refresh * 60 * 1000),
        daysAgo=days_ago,
    )


def streamers():
    return Response(
        json.dumps(
            [
                {"name": s, "points": get_challenge_points(s)}
                for s in sorted(streamers_available())
            ]
        ),
        status=200,
        mimetype="application/json",
    )


class AnalyticsServer(Thread):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        refresh: int = 5,
        days_ago: int = 7,
    ):
        super(AnalyticsServer, self).__init__()

        self.host = host
        self.port = port
        self.refresh = refresh
        self.days_ago = days_ago

        self.app = Flask(
            __name__,
            template_folder=os.path.join(Path().absolute(), "assets"),
            static_folder=os.path.join(Path().absolute(), "assets"),
        )
        self.app.add_url_rule(
            "/",
            "index",
            index,
            defaults={"refresh": refresh, "days_ago": days_ago},
            methods=["GET"],
        )
        self.app.add_url_rule("/streamers", "streamers", streamers, methods=["GET"])
        self.app.add_url_rule(
            "/json/<string:streamer>", "json", read_json, methods=["GET"]
        )
        self.app.add_url_rule("/json_all", "json_all", json_all, methods=["GET"])

    def run(self):
        logger.info(
            f"Analytics running on http://{self.host}:{self.port}/",
            extra={"emoji": ":globe_with_meridians:"},
        )
        self.app.run(host=self.host, port=self.port, threaded=True)
