import requests, re, os, sys, json, gevent, pickle
from gevent import monkey
gevent.monkey.patch_all(thread=False)

from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# Constants to be used in case of request failures
SERVER_FAILURE = "SERVER_FAILURE"
NOT_FOUND = "NOT_FOUND"
OTHER_FAILURE = "OTHER_FAILURE"
REQUEST_FAILURES = (SERVER_FAILURE, NOT_FOUND, OTHER_FAILURE)

# -----------------------------------------------------------------------------
def get_request(url, headers={}, timeout=current.TIMEOUT, params={}):
    """
        Make a HTTP GET request to a url

        @param url (String): URL to make get request to
        @param headers (Dict): Headers to be passed along
                               with the request headers

        @return: Response object or -1 or {}
    """

    i = 0
    while i < current.MAX_TRIES_ALLOWED:
        try:
            response = requests.get(url,
                                    headers=headers,
                                    params=params,
                                    proxies=current.PROXY,
                                    timeout=timeout)
        except Exception as e:
            print e, url
            return SERVER_FAILURE

        if response.status_code == 200:
            return response
        elif response.status_code == 404 or response.status_code == 400:
            # User not found
            # 400 for CodeForces users
            return NOT_FOUND
        i += 1

    # Request unsuccessful even after MAX_TRIES_ALLOWED
    return OTHER_FAILURE

class User:

    def __init__(self, user_id, handles, custom=False):
        self.handles = handles
        if custom:
            self.pickle_file_path = "./applications/stopstalk/graph_data/" + \
                                    str(user_id) + "_custom.pickle"
        else:
            self.pickle_file_path = "./applications/stopstalk/graph_data/" + \
                                    str(user_id) + ".pickle"
        self.contest_mapping = {}
        self.previous_graph_data = None
        self.graph_data = dict([(x.lower() + "_data", []) for x in current.SITES])

        if os.path.exists(self.pickle_file_path):
            self.previous_graph_data = pickle.load(open(self.pickle_file_path, "rb"))
            self.graph_data = dict(self.previous_graph_data)
            for site_data in self.previous_graph_data:
                for contest_data in self.previous_graph_data[site_data]:
                    self.contest_mapping[contest_data["title"]] = contest_data["data"]

    def codechef_data(self):
        handle = self.handles["codechef_handle"]
        url = "https://www.codechef.com/users/" + handle
        response = get_request(url)
        if response in REQUEST_FAILURES:
            print "Request ERROR: CodeChef " + url + " " + response
            return

        def zero_pad(string):
            return "0" + string if len(string) == 1 else string

        try:
            ratings = eval(re.search("var all_rating = .*?;", response.text).group()[17:-1])
        except Exception as e:
            print e
            return

        long_contest_data = {}
        cookoff_contest_data = {}
        ltime_contest_data = {}

        for contest in ratings:
            this_obj = None
            if contest["code"].__contains__("COOK"):
                # Cook off contest
                this_obj = cookoff_contest_data
            elif contest["code"].__contains__("LTIME"):
                # Lunchtime contest
                this_obj = ltime_contest_data
            else:
                # Long contest
                this_obj = long_contest_data
            # getdate, getmonth and getyear give end_date only
            time_stamp = str(datetime.strptime(contest["end_date"], "%Y-%m-%d %H:%M:%S"))
            this_obj[time_stamp] = {"name": contest["name"],
                                    "url": "https://www.codechef.com/" + contest["code"],
                                    "rating": str(contest["rating"]),
                                    "rank": contest["rank"]}

        self.graph_data["codechef_data"] = [{"title": "CodeChef Long",
                                             "data": long_contest_data},
                                            {"title": "CodeChef Cook-off",
                                             "data": cookoff_contest_data},
                                            {"title": "CodeChef Lunchtime",
                                             "data": ltime_contest_data}]
        print self.graph_data["codechef_data"]

    def codeforces_data(self):
        handle = self.handles["codeforces_handle"]
        website = "http://codeforces.com/"
        url = "%sapi/contest.list" % website
        response = get_request(url)
        if response in REQUEST_FAILURES:
            print "Request ERROR: Codeforces " + url + " " + response
            return

        contest_list = response.json()["result"]
        all_contests = {}

        for contest in contest_list:
            all_contests[contest["id"]] = contest

        url = "%scontests/with/%s" % (website, handle)

        response = get_request(url)
        if response in REQUEST_FAILURES:
            print "Request ERROR: Codeforces " + url + " " + response
            return

        soup = BeautifulSoup(response.text, "lxml")
        try:
            tbody = soup.find("table", class_="tablesorter").find("tbody")
        except AttributeError:
            print "Cannot find CodeForces user " + handle
            return

        contest_data = {}
        for tr in tbody.find_all("tr"):
            all_tds = tr.find_all("td")
            contest_id = int(all_tds[1].find("a")["href"].split("/")[-1])
            rank = int(all_tds[2].find("a").contents[0].strip())
            solved_count = int(all_tds[3].find("a").contents[0].strip())
            rating_change = int(all_tds[4].find("span").contents[0].strip())
            new_rating = int(all_tds[5].contents[0].strip())
            contest = all_contests[contest_id]
            time_stamp = str(datetime.fromtimestamp(contest["startTimeSeconds"]))
            contest_data[time_stamp] = {"name": contest["name"],
                                        "url": "%scontest/%d" % (website,
                                                                 contest_id),
                                        "rating": str(new_rating),
                                        "ratingChange": rating_change,
                                        "rank": rank,
                                        "solvedCount": solved_count}

        self.graph_data["codeforces_data"] = [{"title": "Codeforces",
                                               "data": contest_data}]
        print self.graph_data["codeforces_data"]

    def hackerrank_data(self):
        handle = self.handles["hackerrank_handle"]
        website = "https://www.hackerrank.com/"
        url = "%srest/hackers/%s/rating_histories_elo" % (website, handle)
        response = get_request(url)
        if response in REQUEST_FAILURES:
            print "Request ERROR: HackerRank " + url + " " + response
            return
        response = response.json()["models"]

        hackerrank_graphs = []
        for contest_class in response:
            final_json = {}
            for contest in contest_class["events"]:
                time_stamp = contest["date"][:-5].split("T")
                time_stamp = datetime.strptime(time_stamp[0] + " " + time_stamp[1],
                                               "%Y-%m-%d %H:%M:%S")
                # Convert UTC to IST
                time_stamp += timedelta(hours=5, minutes=30)
                time_stamp = str(time_stamp)
                final_json[time_stamp] = {"name": contest["contest_name"],
                                          "url": website + contest["contest_slug"],
                                          "rating": str(contest["rating"]),
                                          "rank": contest["rank"]}

            graph_name = "HackerRank - %s" % contest_class["category"]
            hackerrank_graphs.append({"title": graph_name,
                                      "data": final_json})

        self.graph_data["hackerrank_data"] = hackerrank_graphs
        print hackerrank_graphs

    def spoj_data(self):
        pass

    def hackerearth_data(self):
        pass

    def uva_data(self):
        pass

    def write_to_filesystem(self):
        if self.previous_graph_data == self.graph_data:
            print "No updates in the graph data"
            return

        if self.previous_graph_data is not None:
            # Pickle file already exists for the user
            for site_data in self.graph_data:
                for contest_data in self.graph_data[site_data]:
                    try:
                        previous_value = self.contest_mapping[contest_data["title"]]
                    except KeyError:
                        continue
                    if len(contest_data["data"]) < len(previous_value):
                        contest_data = previous_value
        pickle.dump(self.graph_data, open(self.pickle_file_path, "wb"))

        print "Writing to filesystem done"

    def update_graph_data(self, sites):
        threads = []
        for site in sites:
            if self.handles.has_key(site + "_handle"):
                threads.append(gevent.spawn(getattr(self,
                                                    site + "_data")))

        gevent.joinall(threads)
        self.write_to_filesystem()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sites = sys.argv[1].strip().split(",")
    else:
        sites = [site.lower() for site in current.SITES]
    u = User(1, {"codechef_handle": "tryingtocode", "codeforces_handle": "raj454raj", "hackerrank_handle": "tryingtocode"})
    u = User(157, {"codechef_handle": "darkshadows", "codeforces_handle": "darkshadows", "hackerrank_handle": "darkshadows"})
    u.update_graph_data(sites)
    # db = current.db
    # atable = db.auth_user
    # cftable = db.custom_friend
    # users = db(atable).select()
    # custom_users = db(cftable).select()

    # def get_user_data(list_of_users, custom=False):
    #     for user in list_of_users:
    #         handles = {}
    #         print "Updating for " + user.stopstalk_handle
    #         for site in current.SITES:
    #             site_handle = site.lower() + "_handle"
    #             if user[site_handle]:
    #                 handles[site_handle] = user[site_handle]
    #         user_class = User(handles)
    #         user_class.get_graph_data(user.id, custom=custom)

    # get_user_data(users)
    # get_user_data(custom_users, True)
