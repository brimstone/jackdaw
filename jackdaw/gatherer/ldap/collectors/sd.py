
import base64
from hashlib import sha1
from jackdaw.dbmodel.adsd import JackDawSD
from jackdaw.dbmodel import windowed_query
from jackdaw import logger
from jackdaw.gatherer.ldap.progress import LDAPGathererProgress
from jackdaw.gatherer.ldap.agent.common import *
from jackdaw.gatherer.ldap.agent.agent import LDAPGathererAgent
from jackdaw.dbmodel.graphinfo import JackDawGraphInfo
from jackdaw.dbmodel.adgroup import JackDawADGroup
from jackdaw.dbmodel.adinfo import JackDawADInfo
from jackdaw.dbmodel.aduser import JackDawADUser
from jackdaw.dbmodel.adcomp import JackDawADMachine
from jackdaw.dbmodel.adou import JackDawADOU
from jackdaw.dbmodel.adgpo import JackDawADGPO
from jackdaw.dbmodel.adtrust import JackDawADTrust
from jackdaw.dbmodel import get_session
from jackdaw.dbmodel.edge import JackDawEdge
from jackdaw.dbmodel.edgelookup import JackDawEdgeLookup
import gzip
from tqdm import tqdm
import os
import datetime
from sqlalchemy import func
import asyncio
import json


class SDCollector:
	def __init__(self, session, ldap_mgr, ad_id = None, graph_id = None, agent_cnt = None, sd_target_file_handle = None, resumption = False, progress_queue = None, show_progress = True):
		self.session = session
		self.ldap_mgr = ldap_mgr
		self.agent_cnt = agent_cnt
		self.ad_id = ad_id
		self.domain_name = None
		self.graph_id = graph_id
		self.sd_target_file_handle = sd_target_file_handle
		self.resumption = resumption
		self.progress_queue = progress_queue
		self.show_progress = show_progress

		if self.agent_cnt is None:
			self.agent_cnt = min(len(os.sched_getaffinity(0)), 3)

		self.progress_last_updated = None
		self.agent_in_q = None
		self.agent_out_q = None
		self.sd_file = None
		self.sd_file_path = None
		self.total_targets = None
		self.agents = []

	async def store_sd(self, sd):
		if sd['adsec'] is None:
			return
		jdsd = JackDawSD()

		jdsd.ad_id = self.ad_id
		jdsd.guid =  sd['guid']
		jdsd.sid = sd['sid']
		jdsd.object_type = sd['object_type']
		jdsd.sd = base64.b64encode(sd['adsec']).decode()

		jdsd.sd_hash = sha1(sd['adsec']).hexdigest()

		self.sd_file.write(jdsd.to_json().encode() + b'\r\n')
	
	async def resumption_target_gen(self,q, id_filed, obj_type, jobtype):
		for dn, sid, guid in windowed_query(q, id_filed, 10, is_single_entity = False):
			#print(dn)
			data = {
				'dn' : dn,
				'sid' : sid,
				'guid' : guid,
				'object_type' : obj_type
			}
			self.sd_target_file_handle.write(json.dumps(data).encode() + b'\r\n')
			self.total_targets += 1

	async def resumption_target_gen_2(self,q, id_filed, obj_type, jobtype):
		for dn, guid in windowed_query(q, id_filed, 10, is_single_entity = False):
			#print(dn)
			data = {
				'dn' : dn,
				'sid' : None,
				'guid' : guid,
				'object_type' : obj_type
			}
			self.sd_target_file_handle.write(json.dumps(data).encode() + b'\r\n')
			self.total_targets += 1

	async def generate_sd_targets(self):
		try:
			subq = self.session.query(JackDawSD.guid).filter(JackDawSD.ad_id == self.ad_id)
			q = self.session.query(JackDawADInfo.distinguishedName, JackDawADInfo.objectSid, JackDawADInfo.objectGUID).filter_by(id = self.ad_id).filter(~JackDawADInfo.objectGUID.in_(subq))
			await self.resumption_target_gen(q, JackDawADInfo.id, 'domain', LDAPAgentCommand.SDS)
			q = self.session.query(JackDawADUser.dn, JackDawADUser.objectSid, JackDawADUser.objectGUID).filter_by(ad_id = self.ad_id).filter(~JackDawADUser.objectGUID.in_(subq))
			await self.resumption_target_gen(q, JackDawADUser.id, 'user', LDAPAgentCommand.SDS)
			q = self.session.query(JackDawADMachine.dn, JackDawADMachine.objectSid, JackDawADMachine.objectGUID).filter_by(ad_id = self.ad_id).filter(~JackDawADMachine.objectGUID.in_(subq))
			await self.resumption_target_gen(q, JackDawADMachine.id, 'machine', LDAPAgentCommand.SDS)
			q = self.session.query(JackDawADGroup.dn, JackDawADGroup.objectSid, JackDawADGroup.objectGUID).filter_by(ad_id = self.ad_id).filter(~JackDawADGroup.objectGUID.in_(subq))
			await self.resumption_target_gen(q, JackDawADGroup.id, 'group', LDAPAgentCommand.SDS)
			q = self.session.query(JackDawADOU.dn, JackDawADOU.objectGUID).filter_by(ad_id = self.ad_id).filter(~JackDawADOU.objectGUID.in_(subq))
			await self.resumption_target_gen_2(q, JackDawADOU.id, 'ou', LDAPAgentCommand.SDS)
			q = self.session.query(JackDawADGPO.dn, JackDawADGPO.objectGUID).filter_by(ad_id = self.ad_id).filter(~JackDawADGPO.objectGUID.in_(subq))
			await self.resumption_target_gen_2(q, JackDawADGPO.id, 'gpo', LDAPAgentCommand.SDS)

			logger.debug('generate_sd_targets finished!')
		except Exception as e:
			logger.exception('generate_sd_targets')

	async def prepare_targets(self):
		try:
			if self.resumption is True:
				self.total_targets = 1
				if self.sd_target_file_handle is not None:
					raise Exception('Resumption doesnt use the target file handle!') 
				
				self.sd_target_file_handle = gzip.GzipFile('sd_targets','wb')
				await self.generate_sd_targets()

			else:
				self.total_targets = 0
				self.sd_target_file_handle.seek(0,0)
				for line in self.sd_target_file_handle:
					self.total_targets += 1

			return True, None
		
		except Exception as err:
			logger.exception('prep targets')
			return False, err
	
	async def stop_sds_collection(self):
		for _ in range(len(self.agents)):
			await self.agent_in_q.put(None)

		for agent in self.agents:
			agent.cancel()

		if self.show_progress is True and self.sds_progress is not None:
			self.sds_progress.refresh()
			self.sds_progress.disable = True

		try:
			if self.sd_file is not None:
				self.sd_file.close()
				cnt = 0
				with gzip.GzipFile(self.sd_file_path, 'r') as f:
					for line in tqdm(f, desc='Uploading security descriptors to DB', total=self.total_targets):
						sd = JackDawSD.from_json(line.strip())
						self.session.add(sd)
						cnt += 1
						if cnt % 100 == 0:
							self.session.commit()
				
				self.session.commit()
			
		except Exception as e:
			logger.exception('Error while uploading sds from file to DB')
		finally:
			os.remove(self.sd_file_path)

	async def start_jobs(self):
		self.sd_target_file_handle.seek(0,0)
		for line in self.sd_target_file_handle:
			line = line.strip()
			line = line.decode()
			data = json.loads(line)

			job = LDAPAgentJob(LDAPAgentCommand.SDS, data)
			await self.agent_in_q.put(job)

	async def run(self):
		try:

			qs = self.agent_cnt
			self.agent_in_q = asyncio.Queue() #AsyncProcessQueue()
			self.agent_out_q = asyncio.Queue(qs) #AsyncProcessQueue(1000)
			self.sd_file_path = 'sd_' + datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S") + '.gzip'
			self.sd_file = gzip.GzipFile(self.sd_file_path, 'w')

			logger.debug('Polling sds')
			_, res = await self.prepare_targets()
			if res is not None:
				raise res
		
			for _ in range(self.agent_cnt):
				agent = LDAPGathererAgent(self.ldap_mgr, self.agent_in_q, self.agent_out_q)
				self.agents.append(asyncio.create_task(agent.arun()))
			
			asyncio.create_task(self.start_jobs())
			
			if self.show_progress is True:
				self.sds_progress = tqdm(desc='Collecting SDs', total=self.total_targets, position=0, leave=True)
			if self.progress_queue is not None:
				msg = LDAPGathererProgress()
				msg.type = 'LDAP_SD'
				msg.msg_type = 'STARTED'
				msg.adid = self.ad_id
				msg.domain_name = self.domain_name
				await self.progress_queue.put(msg)
			
			
			acnt = self.total_targets
			while acnt > 0:
				try:
					res = await self.agent_out_q.get()
					res_type, res = res
					
					if res_type == LDAPAgentCommand.SD:
						await self.store_sd(res)
						if self.show_progress is True:
							self.sds_progress.update()
						if self.progress_queue is not None:
							if acnt % 1000 == 0:
								now = datetime.datetime.utcnow()
								td = (now - self.progress_last_updated).total_seconds()
								self.progress_last_updated = now
								msg = LDAPGathererProgress()
								msg.type = 'LDAP_SD'
								msg.msg_type = 'PROGRESS'
								msg.adid = self.ad_id
								msg.domain_name = self.domain_name
								msg.speed = str(1000 // td)
								await self.progress_queue.put(msg)

					elif res_type == LDAPAgentCommand.EXCEPTION:
						logger.warning(str(res))
					
					acnt -= 1
				except Exception as e:
					logger.exception('SDs enumeration error!')
					raise e
			
			return True, None
		except Exception as e:
			logger.exception('SDs enumeration main error')
			return False, e
		
		finally:
			await self.stop_sds_collection()