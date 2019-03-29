import networkx as nx
from jackdaw.dbmodel.adinfo import JackDawADInfo
from jackdaw.dbmodel import *
import holoviews as hv
from bokeh.io import show, output_file
from bokeh.plotting import figure
from bokeh.models.graphs import from_networkx
import pylab as plt

class MembershipPlotter:
	def __init__(self, db_conn):
		self.db_conn = db_conn
		self.graph = nx.MultiDiGraph()
		self.show_group_memberships = True
		self.show_user_memberships = True
		self.show_machine_memberships = True
		self.show_session_memberships = True
		
	def run(self, ad_id):
		session = get_session(self.db_conn)
		adinfo = session.query(JackDawADInfo).get(ad_id)
		
		node_lables = {}
		node_color_map = []
		
		if self.show_user_memberships == True:
			#adding group nodes
			for group in adinfo.groups:
				self.graph.add_node(group.sid, name=group.name, guid=group.guid)
				if group.sid in node_lables:
					raise Exception()
				node_lables[group.sid] = group.name
				node_color_map.append('r')
		
		if self.show_user_memberships == True:
			#adding user nodes
			for user in adinfo.users:
				self.graph.add_node(user.objectSid, name= user.sAMAccountName)
				if user.objectSid in node_lables:
					raise Exception()
				node_lables[user.objectSid] = user.sAMAccountName
				node_color_map.append('b')
				
		if self.show_machine_memberships == True:
			#adding user nodes
			for user in adinfo.computers:
				self.graph.add_node(user.objectSid, name= user.sAMAccountName)
				if user.objectSid in node_lables:
					raise Exception()
				node_lables[user.objectSid] = user.sAMAccountName
				node_color_map.append('k')
		
		"""
		if self.show_session_memberships == True:
			session.query(
			
			
			
			source = Column(String, index=True)
			ip = Column(String, index=True)
			rdns = Column(String, index=True)
			username = Column(String, index=True)
		"""
		#adding membership edges
		for tokengroup in adinfo.group_lookups:
			if tokengroup.is_user == True and self.show_user_memberships == True:
				self.graph.add_edge(tokengroup.sid, tokengroup.member_sid)
			elif tokengroup.is_machine == True and self.show_machine_memberships == True:
				self.graph.add_edge(tokengroup.sid, tokengroup.member_sid)
			elif tokengroup.is_group == True and self.show_group_memberships == True:
				self.graph.add_edge(tokengroup.sid, tokengroup.member_sid)

		#adding group-group membership edges
		#for group in adinfo.groups:
			
		nx.draw(self.graph, node_size = 600, node_color = node_color_map, labels=node_lables, with_labels = True, prog='neato')
		plt.show()
		#plot = figure(title="Networkx Integration Demonstration", x_range=(-2.10,2.10), y_range=(-2.1,2.1),
		#				tools="", toolbar_location=None)
		
		#g = from_networkx(self.graph, nx.spring_layout, scale=2, center=(0,0))
		
		#plot.renderers.append(g)
		#show(plot)