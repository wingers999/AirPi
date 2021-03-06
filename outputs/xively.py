import output
import requests
import json

# add logging support
import logging
mod_log = logging.getLogger('airpi.xively')

class Xively(output.Output):
    requiredData = ["APIKey", "FeedID"]
    optionalData = []

    def __init__(self, data):
        self.log = logging.getLogger('airpi.xively')
        self.URL = "https://api.xively.com/v2/feeds/" + data["FeedID"] + ".json"
        self.headers = ({"X-ApiKey": data["APIKey"]})

    def outputData(self, dataPoints):
        arr = []
        a = l = z = None

        try:
            for i in dataPoints:
                # handle GPS data
                if i["type"] == "Location":
                    l = dict(i)
                    # remove elements not required by Xively
                    del l["type"]
                    del l["sensor"]
                else:
                    arr.append({"id": i["type"], "current_value": i["value"]})

            a = json.dumps({"version": "1.0.0", "datastreams": arr, "location": l})
            self.log.debug("Xively output: [{0}]".format(a,))

            z = requests.put(self.URL, headers = self.headers, data = a)

            if z.text != "":
                self.log.error("Xively Error: {0}".format(z.text))
                return False
            return True
        except requests.exceptions.ConnectionError as ce:
            if "Max retries exceeded" in ce.message:
                pass
            else:
                raise
        except Exception as e:
            self.log.error("Xively Exception: {0}".format(e))
            raise
