# For documentation on Twitch GraphQL API see:
# https://www.apollographql.com/docs/
# https://github.com/mauricew/twitch-graphql-api
# Full list of available methods: https://azr.ivr.fi/schema/query.doc.html (a bit outdated)


import copy
import logging
import os
import random
import re
import time
from pathlib import Path
from secrets import token_hex

import requests

from TwitchChannelPointsMiner.classes.entities.Campaign import Campaign
from TwitchChannelPointsMiner.classes.entities.Drop import Drop
from TwitchChannelPointsMiner.classes.Exceptions import (
    StreamerDoesNotExistException,
    StreamerIsOfflineException,
)
from TwitchChannelPointsMiner.classes.Settings import Priority, Settings
from TwitchChannelPointsMiner.classes.TwitchLogin import TwitchLogin
from TwitchChannelPointsMiner.constants import API, CLIENT_ID, GQLOperations
from TwitchChannelPointsMiner.utils import (
    _millify,
    create_chunks,
    internet_connection_available,
)

logger = logging.getLogger(__name__)


class Twitch(object):
    __slots__ = ["cookies_file", "user_agent", "twitch_login", "running"]

    def __init__(self, username, user_agent, password=None):
        cookies_path = os.path.join(Path().absolute(), "cookies")
        Path(cookies_path).mkdir(parents=True, exist_ok=True)
        self.cookies_file = os.path.join(cookies_path, f"{username}.pkl")
        self.user_agent = user_agent
        self.twitch_login = TwitchLogin(
            CLIENT_ID, username, self.user_agent, password=password
        )
        self.running = True

    def login(self):
        if os.path.isfile(self.cookies_file) is False:
            if self.twitch_login.login_flow():
                self.twitch_login.save_cookies(self.cookies_file)
        else:
            self.twitch_login.load_cookies(self.cookies_file)
            self.twitch_login.set_token(self.twitch_login.get_auth_token())

    # === STREAMER / STREAM / INFO === #
    def update_stream(self, streamer):
        if streamer.stream.update_required() is True:
            stream_info = self.get_stream_info(streamer)
            if stream_info is not None:
                streamer.stream.update(
                    broadcast_id=stream_info["stream"]["id"],
                    title=stream_info["broadcastSettings"]["title"],
                    game=stream_info["broadcastSettings"]["game"],
                    tags=stream_info["stream"]["tags"],
                    viewers_count=stream_info["stream"]["viewersCount"],
                )

                event_properties = {
                    "channel_id": streamer.channel_id,
                    "broadcast_id": streamer.stream.broadcast_id,
                    "player": "site",
                    "user_id": self.twitch_login.get_user_id(),
                }

                if (
                    streamer.stream.game_name() is not None
                    and streamer.settings.claim_drops is True
                ):
                    event_properties["game"] = streamer.stream.game_name()
                    # Update also the campaigns_ids so we are sure to tracking the correct campaign
                    streamer.stream.campaigns_ids = (
                        self.__get_campaign_ids_from_streamer(streamer)
                    )

                streamer.stream.payload = [
                    {"event": "minute-watched", "properties": event_properties}
                ]

    def get_spade_url(self, streamer):
        try:
            headers = {"User-Agent": self.user_agent}
            main_page_request = requests.get(streamer.streamer_url, headers=headers)
            response = main_page_request.text
            regex_settings = "(https://static.twitchcdn.net/config/settings.*?js)"
            settings_url = re.search(regex_settings, response).group(1)

            settings_request = requests.get(settings_url, headers=headers)
            response = settings_request.text
            regex_spade = '"spade_url":"(.*?)"'
            streamer.stream.spade_url = re.search(regex_spade, response).group(1)
        except requests.exceptions.RequestException as e:
            logger.error(f"Something went wrong during extraction of 'spade_url': {e}")

    def get_broadcast_id(self, streamer):
        json_data = copy.deepcopy(GQLOperations.WithIsStreamLiveQuery)
        json_data["variables"] = {"id": streamer.channel_id}
        response = self.post_gql_request(json_data)
        if response != {}:
            stream = response["data"]["user"]["stream"]
            if stream is not None:
                return stream["id"]
            else:
                raise StreamerIsOfflineException

    def get_stream_info(self, streamer):
        json_data = copy.deepcopy(GQLOperations.VideoPlayerStreamInfoOverlayChannel)
        json_data["variables"] = {"channel": streamer.username}
        response = self.post_gql_request(json_data)
        if response != {}:
            if response["data"]["user"]["stream"] is None:
                raise StreamerIsOfflineException
            else:
                return response["data"]["user"]

    def check_streamer_online(self, streamer):
        if time.time() < streamer.offline_at + 60:
            return

        if streamer.is_online is False:
            try:
                self.get_spade_url(streamer)
                self.update_stream(streamer)
            except StreamerIsOfflineException:
                streamer.set_offline()
            else:
                streamer.set_online()
        else:
            try:
                self.update_stream(streamer)
            except StreamerIsOfflineException:
                streamer.set_offline()

    def get_channel_id(self, streamer_username):
        json_response = self.__do_helix_request(f"/users?login={streamer_username}")
        if "data" not in json_response:
            raise StreamerDoesNotExistException
        else:
            data = json_response["data"]
            if len(data) >= 1:
                return data[0]["id"]
            else:
                raise StreamerDoesNotExistException

    def get_followers(self, first=100):
        followers = []
        pagination = {}
        while 1:
            query = f"/users/follows?from_id={self.twitch_login.get_user_id()}&first={first}"
            if pagination != {}:
                query += f"&after={pagination['cursor']}"

            json_response = self.__do_helix_request(query)
            pagination = json_response["pagination"]
            followers += [fw["to_login"].lower() for fw in json_response["data"]]
            time.sleep(random.uniform(0.3, 0.7))

            if pagination == {}:
                break

        return followers

    def update_raid(self, streamer, raid):
        if streamer.raid != raid:
            streamer.raid = raid
            json_data = copy.deepcopy(GQLOperations.JoinRaid)
            json_data["variables"] = {"input": {"raidID": raid.raid_id}}
            self.post_gql_request(json_data)

            logger.info(
                f"Joining raid from {streamer} to {raid.target_login}!",
                extra={"emoji": ":performing_arts:"},
            )

    def viewer_is_mod(self, streamer):
        json_data = copy.deepcopy(GQLOperations.ModViewChannelQuery)
        json_data["variables"] = {"channelLogin": streamer.username}
        response = self.post_gql_request(json_data)
        try:
            streamer.viewer_is_mod = response["data"]["user"]["self"]["isModerator"]
        except (ValueError, KeyError):
            streamer.viewer_is_mod = False

    # === 'GLOBALS' METHODS === #
    # Create chunk of sleep of speed-up the break loop after CTRL+C
    def __chuncked_sleep(self, seconds, chunk_size=3):
        sleep_time = max(seconds, 0) / chunk_size
        for i in range(0, chunk_size):
            time.sleep(sleep_time)
            if self.running is False:
                break

    def __check_connection_handler(self, chunk_size):
        # The success rate It's very hight usually. Why we have failed?
        # Check internet connection ...
        while internet_connection_available() is False:
            random_sleep = random.randint(1, 3)
            logger.warning(
                f"No internet connection available! Retry after {random_sleep}m"
            )
            self.__chuncked_sleep(random_sleep * 60, chunk_size=chunk_size)

    def __do_helix_request(self, query, response_as_json=True):
        url = f"{API}/helix/{query.strip('/')}"
        response = self.twitch_login.session.get(url)
        logger.debug(
            f"Query: {query}, Status code: {response.status_code}, Content: {response.json()}"
        )
        return response.json() if response_as_json is True else response

    def post_gql_request(self, json_data):
        try:
            response = requests.post(
                GQLOperations.url,
                json=json_data,
                headers={
                    "Authorization": f"OAuth {self.twitch_login.get_auth_token()}",
                    "Client-Id": CLIENT_ID,
                    "User-Agent": self.user_agent,
                },
            )
            logger.debug(
                f"Data: {json_data}, Status code: {response.status_code}, Content: {response.text}"
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error with GQLOperations ({json_data['operationName']}): {e}"
            )
            return {}

    def send_minute_watched_events(self, streamers, priority, chunk_size=3):
        while self.running:
            try:
                streamers_index = [
                    i
                    for i in range(0, len(streamers))
                    if streamers[i].is_online is True
                    and (
                        streamers[i].online_at == 0
                        or (time.time() - streamers[i].online_at) > 30
                    )
                ]

                for index in streamers_index:
                    if (streamers[index].stream.update_elapsed() / 60) > 10:
                        # Why this user It's currently online but the last updated was more than 10minutes ago?
                        # Please perform a manually update and check if the user it's online
                        self.check_streamer_online(streamers[index])

                streamers_watching = []
                for prior in priority:
                    if prior == Priority.ORDER and len(streamers_watching) < 2:
                        # Get the first 2 items, they are already in order
                        streamers_watching += streamers_index[:2]

                    elif (
                        prior in [Priority.POINTS_ASCENDING, Priority.POINTS_DESCEDING]
                        and len(streamers_watching) < 2
                    ):
                        items = [
                            {"points": streamers[index].channel_points, "index": index}
                            for index in streamers_index
                        ]
                        items = sorted(
                            items,
                            key=lambda x: x["points"],
                            reverse=(
                                True if prior == Priority.POINTS_DESCEDING else False
                            ),
                        )
                        streamers_watching += [item["index"] for item in items][:2]

                    elif prior == Priority.STREAK and len(streamers_watching) < 2:
                        """
                        Check if we need need to change priority based on watch streak
                        Viewers receive points for returning for x consecutive streams.
                        Each stream must be at least 10 minutes long and it must have been at least 30 minutes since the last stream ended.
                        Watch at least 6m for get the +10
                        """
                        for index in streamers_index:
                            if (
                                streamers[index].settings.watch_streak is True
                                and streamers[index].stream.watch_streak_missing is True
                                and (
                                    streamers[index].offline_at == 0
                                    or (
                                        (time.time() - streamers[index].offline_at)
                                        // 60
                                    )
                                    > 30
                                )
                                and streamers[index].stream.minute_watched < 7
                            ):
                                streamers_watching.append(index)
                                if len(streamers_watching) == 2:
                                    break

                    elif prior == Priority.DROPS and len(streamers_watching) < 2:
                        for index in streamers_index:
                            if streamers[index].drops_condition() is True:
                                streamers_watching.append(index)
                                if len(streamers_watching) == 2:
                                    break

                    elif prior == Priority.SUBSCRIBED and len(streamers_watching) < 2:
                        streamers_with_multiplier = [
                            index
                            for index in streamers_index
                            if streamers[index].viewer_has_points_multiplier()
                        ]
                        streamers_with_multiplier = sorted(
                            streamers_with_multiplier,
                            key=lambda x: streamers[x].total_points_multiplier(),
                            reverse=True,
                        )
                        streamers_watching += streamers_with_multiplier[:2]

                """
                Twitch has a limit - you can't watch more than 2 channels at one time.
                We take the first two streamers from the list as they have the highest priority (based on order or WatchStreak).
                """
                streamers_watching = streamers_watching[:2]

                for index in streamers_watching:
                    next_iteration = time.time() + 60 / len(streamers_watching)

                    try:
                        response = requests.post(
                            streamers[index].stream.spade_url,
                            data=streamers[index].stream.encode_payload(),
                            headers={"User-Agent": self.user_agent},
                            timeout=60,
                        )
                        logger.debug(
                            f"Send minute watched request for {streamers[index]} - Status code: {response.status_code}"
                        )
                        if response.status_code == 204:
                            streamers[index].stream.update_minute_watched()

                            """
                            Remember, you can only earn progress towards a time-based Drop on one participating channel at a time.  [ ! ! ! ]
                            You can also check your progress towards Drops within a campaign anytime by viewing the Drops Inventory.
                            For time-based Drops, if you are unable to claim the Drop in time, you will be able to claim it from the inventory page until the Drops campaign ends.
                            """

                            for campaign in streamers[index].stream.campaigns:
                                for drop in campaign.drops:
                                    # We could add .has_preconditions_met condition inside is_printable
                                    if (
                                        drop.has_preconditions_met is not False
                                        and drop.is_printable is True
                                    ):
                                        # print("=" * 125)
                                        logger.info(
                                            f"{streamers[index]} is streaming {streamers[index].stream}"
                                        )
                                        logger.info(f"Campaign: {campaign}")
                                        logger.info(f"Drop: {drop}")
                                        logger.info(f"{drop.progress_bar()}")
                                        # print("=" * 125)

                    except requests.exceptions.ConnectionError as e:
                        logger.error(f"Error while trying to send minute watched: {e}")
                        self.__check_connection_handler(chunk_size)
                    except requests.exceptions.Timeout as e:
                        logger.error(f"Error while trying to send minute watched: {e}")

                    self.__chuncked_sleep(
                        next_iteration - time.time(), chunk_size=chunk_size
                    )

                if streamers_watching == []:
                    self.__chuncked_sleep(60, chunk_size=chunk_size)
            except Exception:
                logger.error("Exception raised in send minute watched", exc_info=True)

    # === CHANNEL POINTS / PREDICTION === #
    # Load the amount of current points for a channel, check if a bonus is available
    def load_channel_points_context(self, streamer):
        json_data = copy.deepcopy(GQLOperations.ChannelPointsContext)
        json_data["variables"] = {"channelLogin": streamer.username}

        response = self.post_gql_request(json_data)
        if response != {}:
            if response["data"]["community"] is None:
                raise StreamerDoesNotExistException
            channel = response["data"]["community"]["channel"]
            community_points = channel["self"]["communityPoints"]
            streamer.channel_points = community_points["balance"]
            streamer.activeMultipliers = community_points["activeMultipliers"]

            if community_points["availableClaim"] is not None:
                self.claim_bonus(streamer, community_points["availableClaim"]["id"])

    def make_predictions(self, event):
        decision = event.bet.calculate(event.streamer.channel_points)
        selector_index = 0 if decision["choice"] == "A" else 1

        logger.info(
            f"Going to complete bet for {event}",
            extra={
                "emoji": ":four_leaf_clover:",
                "color": Settings.logger.color_palette.BET_GENERAL,
            },
        )
        if event.status == "ACTIVE":
            skip, compared_value = event.bet.skip()
            if skip is True:
                logger.info(
                    f"Skip betting for the event {event}",
                    extra={
                        "emoji": ":pushpin:",
                        "color": Settings.logger.color_palette.BET_FILTERS,
                    },
                )
                logger.info(
                    f"Skip settings {event.bet.settings.filter_condition}, current value is: {compared_value}",
                    extra={
                        "emoji": ":pushpin:",
                        "color": Settings.logger.color_palette.BET_FILTERS,
                    },
                )
            else:
                if decision["amount"] >= 10:
                    logger.info(
                        f"Place {_millify(decision['amount'])} channel points on: {event.bet.get_outcome(selector_index)}",
                        extra={
                            "emoji": ":four_leaf_clover:",
                            "color": Settings.logger.color_palette.BET_GENERAL,
                        },
                    )

                    json_data = copy.deepcopy(GQLOperations.MakePrediction)
                    json_data["variables"] = {
                        "input": {
                            "eventID": event.event_id,
                            "outcomeID": decision["id"],
                            "points": decision["amount"],
                            "transactionID": token_hex(16),
                        }
                    }
                    response = self.post_gql_request(json_data)
                    if (
                        "data" in response
                        and "makePrediction" in response["data"]
                        and "error" in response["data"]["makePrediction"]
                        and response["data"]["makePrediction"]["error"] is not None
                    ):
                        error_code = response["data"]["makePrediction"]["error"]["code"]
                        logger.error(
                            f"Failed to place bet, error: {error_code}",
                            extra={
                                "emoji": ":four_leaf_clover:",
                                "color": Settings.logger.color_palette.BET_FAILED,
                            },
                        )
                else:
                    logger.info(
                        f"Bet won't be placed as the amount {_millify(decision['amount'])} is less than the minimum required 10",
                        extra={
                            "emoji": ":four_leaf_clover:",
                            "color": Settings.logger.color_palette.BET_GENERAL,
                        },
                    )
        else:
            logger.info(
                f"Oh no! The event is not active anymore! Current status: {event.status}",
                extra={
                    "emoji": ":disappointed_relieved:",
                    "color": Settings.logger.color_palette.BET_FAILED,
                },
            )

    def claim_bonus(self, streamer, claim_id):
        if Settings.logger.less is False:
            logger.info(
                f"Claiming the bonus for {streamer}!", extra={"emoji": ":gift:"}
            )

        json_data = copy.deepcopy(GQLOperations.ClaimCommunityPoints)
        json_data["variables"] = {
            "input": {"channelID": streamer.channel_id, "claimID": claim_id}
        }
        self.post_gql_request(json_data)

    # === CAMPAIGNS / DROPS / INVENTORY === #
    def __get_campaign_ids_from_streamer(self, streamer):
        json_data = copy.deepcopy(GQLOperations.DropsHighlightService_AvailableDrops)
        json_data["variables"] = {"channelID": streamer.channel_id}
        response = self.post_gql_request(json_data)
        try:
            return (
                []
                if response["data"]["channel"]["viewerDropCampaigns"] is None
                else [
                    item["id"]
                    for item in response["data"]["channel"]["viewerDropCampaigns"]
                ]
            )
        except (ValueError, KeyError):
            return []

    def __get_inventory(self):
        response = self.post_gql_request(GQLOperations.Inventory)
        try:
            return (
                response["data"]["currentUser"]["inventory"] if response != {} else {}
            )
        except (ValueError, KeyError, TypeError):
            return {}

    def __get_drops_dashboard(self, status=None):
        response = self.post_gql_request(GQLOperations.ViewerDropsDashboard)
        campaigns = response["data"]["currentUser"]["dropCampaigns"]
        if status is not None:
            campaigns = list(filter(lambda x: x["status"] == status.upper(), campaigns))
        return campaigns

    def __get_campaigns_details(self, campaigns):
        result = []
        chunks = create_chunks(campaigns, 20)
        for chunk in chunks:
            json_data = []
            for campaign in chunk:
                json_data.append(copy.deepcopy(GQLOperations.DropCampaignDetails))
                json_data[-1]["variables"] = {
                    "dropID": campaign["id"],
                    "channelLogin": f"{self.twitch_login.get_user_id()}",
                }

            response = self.post_gql_request(json_data)
            result += list(map(lambda x: x["data"]["user"]["dropCampaign"], response))
        return result

    def __sync_campaigns(self, campaigns):
        # We need the inventory only for get the real updated value/progress
        # Get data from inventory and sync current status with streamers.campaigns
        inventory = self.__get_inventory()
        if inventory not in [None, {}] and inventory["dropCampaignsInProgress"] not in [
            None,
            {},
        ]:
            # Iterate all campaigns from dashboard (only active, with working drops)
            # In this array we have also the campaigns never started from us (not in nventory)
            for i in range(len(campaigns)):
                campaigns[i].clear_drops()  # Remove all the claimed drops
                # Iterate all campaigns currently in progress from out inventory
                for progress in inventory["dropCampaignsInProgress"]:
                    if progress["id"] == campaigns[i].id:
                        campaigns[i].in_inventory = True
                        campaigns[i].sync_drops(
                            progress["timeBasedDrops"], self.claim_drop
                        )
                        campaigns[i].clear_drops()  # Remove all the claimed drops
                        break
        return campaigns

    def claim_drop(self, drop):
        logger.info(f"Claim {drop}", extra={"emoji": ":package:"})

        json_data = copy.deepcopy(GQLOperations.DropsPage_ClaimDropRewards)
        json_data["variables"] = {"input": {"dropInstanceID": drop.drop_instance_id}}
        response = self.post_gql_request(json_data)
        try:
            # response["data"]["claimDropRewards"] can be null and respose["data"]["errors"] != []
            # or response["data"]["claimDropRewards"]["status"] === DROP_INSTANCE_ALREADY_CLAIMED
            if ("claimDropRewards" in response["data"]) and (
                response["data"]["claimDropRewards"] is None
            ):
                return False
            elif ("errors" in response["data"]) and (response["data"]["errors"] != []):
                return False
            elif ("claimDropRewards" in response["data"]) and (
                response["data"]["claimDropRewards"]["status"]
                in ["ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"]
            ):
                return True
            else:
                return False
        except (ValueError, KeyError):
            return False

    def claim_all_drops_from_inventory(self):
        inventory = self.__get_inventory()
        if inventory not in [None, {}]:
            if inventory["dropCampaignsInProgress"] not in [None, {}]:
                for campaign in inventory["dropCampaignsInProgress"]:
                    for drop_dict in campaign["timeBasedDrops"]:
                        drop = Drop(drop_dict)
                        drop.update(drop_dict["self"])
                        if drop.is_claimable is True:
                            drop.is_claimed = self.claim_drop(drop)
                            time.sleep(random.uniform(5, 10))

    def sync_campaigns(self, streamers, chunk_size=3):
        campaigns_update = 0
        while self.running:
            try:
                # Get update from dashboard each 60minutes
                if (
                    campaigns_update == 0
                    or ((time.time() - campaigns_update) / 60) > 60
                ):
                    campaigns_update = time.time()
                    # Get full details from current ACTIVE campaigns
                    # Use dashboard so we can explore new drops not currently active in our Inventory
                    campaigns_details = self.__get_campaigns_details(
                        self.__get_drops_dashboard(status="ACTIVE")
                    )
                    campaigns = []

                    # Going to clear array and structure. Remove all the timeBasedDrops expired or not started yet
                    for index in range(0, len(campaigns_details)):
                        campaign = Campaign(campaigns_details[index])
                        if campaign.dt_match is True:
                            # Remove all the drops already claimed or with dt not matching
                            campaign.clear_drops()
                            if campaign.drops != []:
                                campaigns.append(campaign)

                # Divide et impera :)
                campaigns = self.__sync_campaigns(campaigns)

                # Check if user It's currently streaming the same game present in campaigns_details
                for i in range(0, len(streamers)):
                    if streamers[i].drops_condition() is True:
                        # yes! The streamer[i] have the drops_tags enabled and we It's currently stream a game with campaign active!
                        # With 'campaigns_ids' we are also sure that this streamer have the campaign active.
                        # yes! The streamer[index] have the drops_tags enabled and we It's currently stream a game with campaign active!
                        streamers[i].stream.campaigns = list(
                            filter(
                                lambda x: x.drops != []
                                and x.game == streamers[i].stream.game
                                and x.id in streamers[i].stream.campaigns_ids,
                                campaigns,
                            )
                        )

            except (ValueError, KeyError, requests.exceptions.ConnectionError) as e:
                logger.error(f"Error while syncing inventory: {e}")
                self.__check_connection_handler(chunk_size)

            self.__chuncked_sleep(60, chunk_size=chunk_size)
