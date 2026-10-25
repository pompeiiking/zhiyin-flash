import asyncio,json
from pathlib import Path
from datetime import datetime,timezone
from tests.test_dialogue_runtime import setup,send,action
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services.conversation_ledger import ConversationLedger
from zhiyin_business.policies.collection import plan_collection
from zhiyin_kernel.assets import Report,Verdict,Swot
from zhiyin_api.dto.mappers import report_full_text_view
from zhiyin_kernel.profile_taxonomy import merge_preferences
from types import SimpleNamespace

async def main():
 out={}
 c,e,s=await setup()
 r=await c.orchestrator.handle_message(TurnRequest(user_id='u1',task_id='task-issue35-audit',message='你好',client_msg_id='audit35'))
 out['35']={'accepted':bool(r),'persisted':(await c.sessions.get('task-issue35-audit')) is not None}
 async def first(rt):return await rt.action(action('profile.update',{'key':'school','value':'重庆工商大学'},evidence='重庆工商大学',authorization='proposal'))
 c,e,s=await setup(first)
 await send(c,s,'我在重庆工商大学，学制四年')
 old=e.receipts[-1]['action_id']
 async def second(rt):return await rt.action(action('profile.update',{'key':'duration','value':'四年'},evidence='四年',authorization='proposal',supersedes_action_id=old))
 e.callback=second
 await send(c,s,'我在重庆工商大学，学制四年')
 ledger=await ConversationLedger(c.student_state).read('u1',s.id)
 out['38']={'cross_field_replacement_accepted':True,'old_key':ledger['actions'][old]['payload']['key'],'old_state':ledger['actions'][old]['state'],'superseded_by':ledger['actions'][old].get('superseded_by'),'new_key':e.receipts[-1].get('change',{}).get('key'),'stored_keys':[f.key for f in await c.profile_service.get_fields('u1')]}
 c,e,s=await setup()
 async def major(rt):return await rt.action(action('profile.update',{'key':'major','value':'市场营销'},evidence='市场营销',authorization='automatic'))
 e.callback=major
 await send(c,s,'我读市场营销')
 fields=await c.profile_service.get_fields('u1')
 profile=await c.profile_service.get('u1')
 collection=plan_collection(profile)
 item=next(x for x in collection.steps if x.key=='major')
 out['39']={'profile_major':next(f.value for f in fields if f.key=='major'),'collection_got':item.got,'source':item.source.value}
 async def invalid_report(rt):
  p=Report(id='audit',user_id='u1',version=1,generated_at=datetime.now(timezone.utc),verdict=Verdict(title='本报告说明',summary='本轮更新的是依据，不是结论'),swot=Swot())
  return await rt.action(action('report.save',p.model_dump(mode='json'),evidence='生成报告',authorization='explicit'))
 c,e,s=await setup(invalid_report)
 await send(c,s,'请生成报告')
 saved=await c.asset_service.get_report('u1')
 view=report_full_text_view(saved).model_dump(mode='json')
 out['41']={'executed':e.receipts[-1]['executed'],'saved_version':saved.version,'stored_title':saved.verdict.title,'display_verdict':view['verdict']}
 vals,attrs,_=merge_preferences('interest',SimpleNamespace(value=['写东西'],attributes={'polarity':'like'}),['应酬','天天应酬'],{'polarity':'dislike'})
 out['40']={'stored_values':vals,'attributes':attrs,'same_concept_deduplicated':len(vals)==2}
 Path('D:/zhiyin-flash-profile-review/output/issues-35-38-39-40-41-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out,ensure_ascii=False,indent=2))
asyncio.run(main())
