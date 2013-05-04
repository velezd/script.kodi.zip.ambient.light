import time
import os
import socket
import json
import random
import hashlib
import xbmc
import xbmcaddon

__addon__      = xbmcaddon.Addon()
__cwd__        = __addon__.getAddonInfo('path')
__icon__       = os.path.join(__cwd__,"icon.png")
__settings__   = os.path.join(__cwd__,"resources","settings.xml")

def log(msg):
  xbmc.log("%s: %s" % ("Hue", msg))
   
def notify(title, msg=""):
  global __icon__
  xbmc.executebuiltin("XBMC.Notification(%s, %s, 3, %s)" % (title, msg, __icon__))
  #log(str(title) + " " + str(msg))

try:
  import requests
except ImportError:
  notify("XBMC Hue", "ERROR: Could not import Python requests")

def start_autodisover():
  port = 1900
  ip = "239.255.255.250"

  address = (ip, port)
  data = """M-SEARCH * HTTP/1.1
  HOST: %s:%s
  MAN: ssdp:discover
  MX: 3
  ST: upnp:rootdevice""" % (ip, port)
  client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

  hue_ip = None
  num_retransmits = 0
  while(num_retransmits < 10) and hue_ip == None:
      num_retransmits += 1
      client_socket.sendto(data, address)
      recv_data, addr = client_socket.recvfrom(2048)
      if "IpBridge" in recv_data and "description.xml" in recv_data:
        hue_ip = recv_data.split("LOCATION: http://")[1].split(":")[0]
      time.sleep(1)
      
  return hue_ip

def register_user(hue_ip):
  username = hashlib.md5(str(random.random())).hexdigest()
  device = "xbmc-player"
  data = '{"username": "%s", "devicetype": "%s"}' % (username, device)

  r = requests.post('http://%s/api' % hue_ip, data=data)
  response = r.text
  while "link button not pressed" in response:
    notify("Bridge discovery", "press link button on bridge")
    r = requests.post('http://%s/api' % hue_ip, data=data)
    response = r.text 
    time.sleep(3)

  return username

def mixed_mode(hue):
  if hue.settings.mode == 0 and hue.settings.ambilight_dim:
    return True
  else:
    return False

class Light:
  start_setting = None
  group = False

  def __init__(self, bridge_ip, bridge_user, light, dimmed_bri, dimmed_hue, undim_bri, undim_hue):
    self.bridge_ip = bridge_ip
    self.bridge_user = bridge_user
    self.light = light
    self.dimmed_bri = dimmed_bri
    self.dimmed_hue = dimmed_hue
    self.undim_bri = undim_bri
    self.undim_hue = undim_hue
    self.get_current_setting()

    self.s = requests.Session()

  def request_url_put(self, url, data):
    if self.start_setting['on']:
      try:
        self.s.put(url, data=data)
      except:
        pass # probably a timeout

  def get_current_setting(self):
    r = requests.get("http://%s/api/%s/lights/%s" % \
      (self.bridge_ip, self.bridge_user, self.light))
    j = r.json()
    self.start_setting = {
      "on": j['state']['on'],
      "bri": j['state']['bri'],
      "hue": j['state']['hue'],
      "sat": j['state']['sat'],
    }

  def set_light(self, data):
    self.request_url_put("http://%s/api/%s/lights/%s/state" % \
      (self.bridge_ip, self.bridge_user, self.light), data=data)

  def set_light2(self, hue, sat, bri):
    data = json.dumps({
        "on": True,
        "hue": hue,
        "sat": sat,
        "bri": bri,
        #"bri": 254,
    })

    self.request_url_put("http://%s/api/%s/lights/%s/state" % \
      (self.bridge_ip, self.bridge_user, self.light), data=data)

  def flash_light(self):
    self.dim_light(10)
    self.brighter_light()

  def dim_light(self):
    #self.get_current_setting()
    dimmed = '{"on":true,"bri":%s,"hue":%s,"transitiontime":4}' % \
      (self.dimmed_bri, self.dimmed_hue)
    self.set_light(dimmed)

  def brighter_light(self):
    on = '{"on":true,"bri":%d,"hue":%s,"transitiontime":4}' % \
      (self.undim_bri, self.undim_hue)
    self.set_light(on)

class Group(Light):
  group = True

  def __init__(self, bridge_ip, bridge_user, group_id, primary, dimmed_bri, dimmed_hue, undim_bri,  undim_hue):
    Light.__init__(
      self,
      bridge_ip,
      bridge_user,
      primary,
      dimmed_bri,
      dimmed_hue,
      undim_bri,
      undim_hue
    )
    self.group_id = group_id

  def set_light(self, data):
    Light.request_url_put(self, "http://%s/api/%s/groups/%s/action" % \
      (self.bridge_ip, self.bridge_user, self.group_id), data=data)

  def set_light2(self, hue, sat, bri):
    data = json.dumps({
        "on": True,
        "hue": hue,
        "sat": sat,
        "bri": bri,
        #"bri": 254,
    })

    self.request_url_put("http://%s/api/%s/groups/%s/action" % \
      (self.bridge_ip, self.bridge_user, self.group_id), data=data)

  def dim_light(self):
    # Setting the brightness of a group to 0 does not turn the lights off
    # workaround: dim the lights first, then turn them off
    dimmed = '{"on":true,"bri":%s,"hue":%s,"transitiontime":4}' % \
      (self.dimmed_bri, self.dimmed_hue)
    self.set_light(dimmed)

    if self.dimmed_bri == 0:
        off = '{"on":false}'
        self.set_light(off)