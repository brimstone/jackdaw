#!/usr/bin/env python3
#
# Author:
#  Tamas Jos (@skelsec)
#

# System modules
import datetime
import tempfile
import os
import pathlib

from jackdaw.dbmodel.graphinfo import JackDawGraphInfo
from jackdaw.nest.graph.domain import DomainGraph
from jackdaw.nest.graph.graphdata import GraphData
from jackdaw.nest.graph.construct import GraphConstruct
from jackdaw.nest.graph.domaindiff import DomainDiff
from jackdaw.dbmodel.adgroup import JackDawADGroup
from jackdaw.dbmodel.edgelookup import JackDawEdgeLookup
from jackdaw.dbmodel.edge import JackDawEdge
from jackdaw.dbmodel.aduser import JackDawADUser
from jackdaw import logger
from jackdaw.nest.graph.edgecalc import EdgeCalc
import connexion


# 3rd party modules
from flask import make_response, abort, current_app, send_file, after_this_request


graph_id_ctr = 1
graphs = {}

diff_id_ctr = 1
diffs = {}

def list_offline():
	t = []
	for res in current_app.db.session.query(JackDawGraphInfo.id).all():
		t.append(res)
	return t

def list_loaded():
	return list(graphs.keys())

def create(adids):
	raise Exception('Not yet implemented!')
	#if len(adids) > 1:
	#	raise Exception('Currently only one ID is supported!')
	#for adid in adids:
	#	try:
	#		adid = str(int(adid))
	#	except Exception as e:
	#		raise e
	#	
	#return {'graphid' : graphid}

def delete(graphid):
	del graphs[graphid]
	return {}


def save(graphid):
	raise Exception('Not yet implemented!')
	#with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
	#	temp_file_name = tmpfile.name
	#
	##logger.debug('Temp file created, but will not be removed! %s' % temp_file_name)
	#graphs[graphid].to_gzip(temp_file_name)
	#
	#attachment_name = 'graph_%s_%s.gzip' % (graphid, datetime.datetime.now().isoformat())
	#resp = send_file(temp_file_name,
	#	as_attachment=True, 
	#	mimetype='application/octet-stream',
	#	attachment_filename=attachment_name
	#)
	#return resp

def upload(file_to_upload):
	pass
	#global graph_id_ctr
	#old_graph_id_ctr = graph_id_ctr
	#graph_id_ctr += 1
	#
	#file_to_upload = connexion.request.files['file_to_upload']
	#graphs[old_graph_id_ctr] = DomainGraph.from_gzip_stream(file_to_upload.stream)
	#graphs[old_graph_id_ctr].dbsession = current_app.db.session #need to restore db session
	#
	#return {'graphid' : old_graph_id_ctr}

def load(graphid):
	global graph_id_ctr
	if current_app.config.get('JACKDAW_GRAPH_BACKEND').upper() == 'networkx'.upper():
		from jackdaw.nest.graph.backends.networkx.domaingraph import JackDawDomainGraphNetworkx
		graph_type = JackDawDomainGraphNetworkx
	elif current_app.config.get('JACKDAW_GRAPH_BACKEND').upper() == 'igraph'.upper():
		from jackdaw.nest.graph.backends.igraph.domaingraph import JackDawDomainGraphIGraph
		graph_type = JackDawDomainGraphIGraph
	elif current_app.config.get('JACKDAW_GRAPH_BACKEND').upper() == 'graphtools'.upper():
		from jackdaw.nest.graph.backends.graphtools.domaingraph import JackDawDomainGraphGrapthTools
		graph_type = JackDawDomainGraphGrapthTools

		
	graph = graph_type(current_app.db.session, graphid, work_dir = current_app.config['JACKDAW_GRAPH_DIR'])
	graph.load()
	old_graph_id_ctr = graph_id_ctr
	graph_id_ctr += 1
	graphs[old_graph_id_ctr] = graph
	return {'graphid' : old_graph_id_ctr}


	#
	#old_graph_id_ctr = graph_id_ctr
	#graph_id_ctr += 1
	#graphs[old_graph_id_ctr] = graph
	#return {'graphid' : old_graph_id_ctr}



	#if current_app.config.get('JACKDAW_GRAPH_BACKEND').upper() == 'networkx'.upper():
	#	from jackdaw.nest.graph.backends.networkx.domaingraph import JackDawDomainGraphNetworkx
	#	graph_type = JackDawDomainGraphNetworkx
	#global graph_id_ctr
	#graph = graph_type(current_app.db.session, current_app.config.get('JACKDAW_GRAPH_DIR'))
	#graph.load(storedid)
	#
	#old_graph_id_ctr = graph_id_ctr
	#graph_id_ctr += 1
	#graphs[old_graph_id_ctr] = graph
	#return {'graphid' : old_graph_id_ctr}


def get(graphid):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	res = graphs[graphid].all_shortest_paths()
	return res.to_dict()

def query_path(graphid, src = None, dst = None, format = 'd3'):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	if src is None and dst is None:
		return {}
	res = graphs[graphid].all_shortest_paths(src, dst)
	return res.to_dict(format = format)

def query_path_da(graphid, format = 'vis'):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	
	da_sids = {}
	#searching for domain admin SID
	
	#for node in graphs[graphid].get_node():
	#	print(node)
	#	if node.id == graphs[graphid].domain_sid + '-512':
	#		da_sids[node.id] = 1
	
	for res in current_app.db.session.query(JackDawADGroup).filter_by(ad_id = graphs[graphid].domain_id).filter(JackDawADGroup.objectSid.like('%-512')).all():
		da_sids[res.objectSid] = 0
	
	if len(da_sids) == 0:
		return 'No domain administrator group found', 404
	
	res = GraphData()
	for sid in da_sids:
		res += graphs[graphid].shortest_paths(None, sid)


	#print(res)
	return res.to_dict(format = format)

def query_path_dcsync(graphid, format = 'vis'):
	pass

def query_path_kerberoast(graphid, format = 'vis'):
	if graphid not in graphs:
		return 'Graph Not Found', 404

	target_sids = {}
	da_sids = {}

	for res in current_app.db.session.query(JackDawADGroup).filter_by(ad_id = graphs[graphid].domain_id).filter(JackDawADGroup.objectSid.like('%-512')).all():
		da_sids[res.objectSid] = 0

	for res in current_app.db.session.query(JackDawADUser.objectSid)\
		.filter_by(ad_id = graphs[graphid].domain_id)\
		.filter(JackDawADUser.servicePrincipalName != None).all():
		
		target_sids[res[0]] = 0

	res = GraphData()
	for dst_sid in da_sids:
		for src_sid in target_sids:
			res += graphs[graphid].shortest_paths(src_sid, dst_sid)

	return res.to_dict(format = format)

def query_path_asreproast(graphid, format = 'vis'):
	if graphid not in graphs:
		return 'Graph Not Found', 404

	target_sids = {}
	da_sids = {}

	for res in current_app.db.session.query(JackDawADGroup).filter_by(ad_id = graphs[graphid].domain_id).filter(JackDawADGroup.objectSid.like('%-512')).all():
		da_sids[res.objectSid] = 0

	for res in current_app.db.session.query(JackDawADUser.objectSid)\
		.filter_by(ad_id = graphs[graphid].domain_id)\
		.filter(JackDawADUser.UAC_DONT_REQUIRE_PREAUTH == True).all():
		
		target_sids[res[0]] = 0

	res = GraphData()
	for dst_sid in da_sids:
		for src_sid in target_sids:
			res += graphs[graphid].shortest_paths(src_sid, dst_sid)

	return res.to_dict(format = format)


def list_nodes(graphid, with_data = False):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	nodes = []
	for node in graphs[graphid].get_node():
		nodes.append(node.to_dict())
	return nodes

def get_node(graphid, nodeid):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	return graphs[graphid].get_node(nodeid)

def query_path_all(graphid):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	return graphs[graphid].show_all().to_dict(format = 'vis')

def search_sid(graphid, sid):
	return {}

def search_cn(graphid, cn):
	return {}

def stat_distance(graphid, sid):
	if graphid not in graphs:
		return 'Graph Not Found', 404
	distances = graphs[graphid].distances_from_node(sid)
	
	return distances

def diff(graphids):
	global diff_id_ctr
	
	db = current_app.db
	dd = DomainDiff(dbsession=db.session)
	construct_old = GraphConstruct(graphids['src'])
	construct_new = GraphConstruct(graphids['dst'])

	diffs[diff_id_ctr] = dd
	diff_id_ctr += 1

	dd.construct(construct_old, construct_new)

	return {
		'diffid' : diff_id_ctr - 1
	}

def list_diff_all():
	return list(diffs.keys())

def diff_nodes(diffid):
	diffres = diffs[diffid].diff_nodes()
	return diffres

def diff_path_distance(diffid, sid):
	diffres = diffs[diffid].diff_path_distance(sid)
	return diffres

def diff_path(diffid, srcsid, dstsid):
	diffres = diffs[diffid].diff_path(srcsid, dstsid)
	return diffres

def diff_path_da(diffid):
	diffres = diffs[diffid].diff_path_da()
	return diffres