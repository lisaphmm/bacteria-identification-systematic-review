"""Aggregate manually authored QUADAS-2 decisions. No domain is classified by code.

Inputs: manual_assessments.tsv (reviewer decisions), existing extraction and tiers.
Outputs: study/domain/question tables, Wilson intervals, descriptive sensitivity,
publication figures and workbook input. Requires bundled pandas/numpy/Pillow.
"""
import csv, hashlib, json, math, re, textwrap
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'results/final/quadas2_review'
TABLES=ROOT/'report_outputs/tables'
FIGS=ROOT/'report_outputs/figures'
DOMAINS={'D1':'Sample selection','D2':'Index test','D3':'Reference standard','D4':'Flow and timing',
         'A1':'Sample applicability','A2':'Index applicability','A3':'Reference applicability'}
LABEL={'L':'Low','H':'High','U':'Unclear'}
COLOURS={'L':'#009E73','H':'#D55E00','U':'#F0C75E'}
QUESTIONS={
 'D1':[('S1','Appropriate consecutive/random/representative source sampling'),('S2','Artificial disease case-control contrast avoided'),('S3','Inappropriate exclusions avoided')],
 'D2':[('I1','Evaluation independent of fitting/model/threshold selection'),('I2','Source grouping before crops/augmentation; training-only fitted preprocessing')],
 'D3':[('R1','Reference valid for the task target'),('R2','Reference independent of index; blinded where relevant')],
 'D4':[('F1','Timing/growth stage appropriate'),('F2','All evaluated units receive intended reference'),('F3','Comparable reference procedure'),('F4','All eligible units analysed or losses justified')]}
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
def font(n):return ImageFont.truetype(FONT,n)
def write(df,path):df.to_csv(path,index=False,encoding='utf-8-sig',float_format='%.8f')
def wilson(k,n):
 z=1.959963984540054;p=k/n;d=1+z*z/n
 c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return max(0,c-h),min(1,c+h)
def overall(values):return 'H' if 'H' in values else 'L' if all(v=='L' for v in values) else 'U'

m=pd.read_csv(OUT/'manual_assessments.tsv',sep='\t',keep_default_na=False)
e=pd.read_csv(TABLES/'extraction_coded.csv',keep_default_na=False)
t=pd.read_csv(ROOT/'results/final/evidence_tiers.csv',keep_default_na=False)
assert len(m)==206 and m.id.is_unique and set(m.id)==set(e.id)
assert all(m[c].isin(LABEL).all() for c in DOMAINS)
assert m.signals.str.fullmatch(r'[YNU]{3}/[YNU]{2}/[YNU]{2}/[YNU]{4}').all()
assert m[[c+'_reason' for c in DOMAINS]].map(lambda s:bool(s.strip())).all().all()
df=m.merge(t[['id','title','year','tier','source_pdf','source_sha256','source_page_count']],on='id',validate='one_to_one')
df=df.merge(e[['id','Authors','DOI','agar','acc_pct','acc','tasks','model_family','dataset','species','ref','valid']],on='id',validate='one_to_one')
df.agar=df.agar.astype(str).str.lower().eq('true')
df.acc_pct=pd.to_numeric(df.acc_pct,errors='coerce')
df['overall_risk']=df.apply(lambda r:overall([r[k] for k in ['D1','D2','D3','D4']]),axis=1)
df['overall_applicability']=df.apply(lambda r:overall([r[k] for k in ['A1','A2','A3']]),axis=1)
df['reviewer']='Codex AI reviewer (single source-based assessment)'
df['assessment_date']='2026-10-28'
df['human_validation']='Not independently validated by human reviewers; no inter-reviewer agreement calculated'
df['prior_information']='Aware of prior extraction/tiering; not blinded; tier did not determine risk'
flags={
 'R00395':'Scope adjudication: principal benchmark lacks an established bacterial target.',
 'R01154':'Local 2025 preprint assessed; cited final publication version not verified.',
 'R01157':'Tracking evaluation lacks independent biological trajectory truth.',
 'R03263':'Harmful/harmless tags are species-based proxies, not observed pathogenicity.',
 'R04668':'Sequencing presence used as a proxy for clinical infection.',
 'R04880':'Species-based urinary tags are not clinical UTI ground truth.',
 'R05350':'Methods report 14 validation cases; Results/table report 42; PDF pages 4-5 visually verified.'}
df['scope_version_note']=df.id.map(flags).fillna('')
df['review_scope']='Targeted manual reading of methodological source passages; not every page/supplement/repository verified'
full_cols=['id','title','year','Authors','DOI','task','unit','agar']+list(DOMAINS)+['overall_risk','overall_applicability','signals','pages']+[k+'_reason' for k in DOMAINS]+['scope_version_note','reviewer','assessment_date','human_validation','prior_information','source_pdf','source_sha256','source_page_count','review_scope','tier','acc_pct','acc','dataset','species','model_family','ref','valid']
write(df[full_cols],OUT/'QUADAS2_study_assessments.csv')
write(df[full_cols],TABLES/'supplementary_table_S3_QUADAS2_AI_assessments.csv')

long=[];sig=[]
for _,r in df.iterrows():
 for k,label in DOMAINS.items():
  long.append(dict(id=r.id,title=r.title,domain=k,domain_name=label,judgement=LABEL[r[k]],
   rationale=r[k+'_reason'],source_pages_or_sections=r.pages,source_pdf=r.source_pdf,
   source_sha256=r.source_sha256,reviewer=r.reviewer,assessment_date=r.assessment_date))
 for k,answers in zip(['D1','D2','D3','D4'],r.signals.split('/')):
  for (qid,question),answer in zip(QUESTIONS[k],answers):
   sig.append(dict(id=r.id,domain=k,question_id=qid,question=question,
    answer={'Y':'Yes','N':'No','U':'Unclear'}[answer],domain_judgement=LABEL[r[k]],
    domain_rationale=r[k+'_reason'],source_pages_or_sections=r.pages,source_pdf=r.source_pdf))
write(pd.DataFrame(long),OUT/'QUADAS2_domain_evidence.csv')
write(pd.DataFrame(sig),OUT/'QUADAS2_signalling_answers.csv')
summary=[]
for group,g in [('All included',df),('Agar plates',df[df.agar]),('Other images',df[~df.agar])]:
 for k in list(DOMAINS)+['overall_risk','overall_applicability']:
  for code,label in LABEL.items():
   n=int(g[k].eq(code).sum());N=len(g);lo,hi=wilson(n,N)
   summary.append(dict(cohort=group,domain=k,domain_name=DOMAINS.get(k,k.replace('_',' ').title()),judgement=label,code=code,n=n,denominator=N,percent=100*n/N,ci_low_percent=100*lo,ci_high_percent=100*hi))
summary=pd.DataFrame(summary);write(summary,TABLES/'quadas2_domain_distribution.csv')
write(df[['id','agar']+list(DOMAINS)+['overall_risk','overall_applicability']],TABLES/'quadas2_traffic_light_data.csv')
write(df[['id','title','agar','overall_risk','acc_pct','acc','task','tier']],TABLES/'quadas2_accuracy_points.csv')
acc=[]
for cohort,g in [('All included',df),('Agar plates',df[df.agar])]:
 for label,g0 in [('All reports',g),('Exclude High risk (Low + Unclear)',g[g.overall_risk!='H']),('High risk',g[g.overall_risk=='H']),('Unclear risk',g[g.overall_risk=='U']),('Low risk only',g[g.overall_risk=='L'])]:
  v=g0.acc_pct.dropna()
  acc.append(dict(cohort=cohort,analysis=label,reports=len(g0),accuracy_n=len(v),missing_accuracy=len(g0)-len(v),median=v.median(),q1=v.quantile(.25),q3=v.quantile(.75),minimum=v.min(),maximum=v.max(),interpretation='Descriptive as-extracted heterogeneous headline values; not pooled accuracy; excluding High does not make remaining studies Low risk'))
acc=pd.DataFrame(acc);write(acc,TABLES/'quadas2_accuracy_sensitivity.csv')

# Publication figures: categorical risks, not numerical quality scores.
im=Image.new('RGB',(2400,1740),'white');d=ImageDraw.Draw(im)
d.text((90,50),'Adapted QUADAS-2: 206 reports',font=font(58),fill='#222222')
d.text((90,126),'Single AI reviewer | Low / High / Unclear | 28 October 2026',font=font(34),fill='#555555')
keys=['D1','D2','D3','D4','overall_risk','A1','A2','A3','overall_applicability']
for j,k in enumerate(keys):
 y=240+j*135;label=DOMAINS.get(k,k.replace('_',' ').title());d.text((90,y+20),label,font=font(37),fill='#222222')
 x=720
 for code in ['L','H','U']:
  n=int(df[k].eq(code).sum());w=1530*n/len(df)
  if n:
   d.rectangle((x,y,x+w,y+83),fill=COLOURS[code])
   if w>95:d.text((x+w/2,y+41),f'{n} ({100*n/206:.1f}%)' if w>=250 else str(n),font=font(31 if w>260 else 28),fill='white' if code in ['L','H'] else '#222222',anchor='mm')
  x+=w
  if n and w<=95:d.text((2280,y+22),f'{code}: {n}',font=font(28),fill='#333333')
for i,code in enumerate(['L','H','U']):
 x=110+620*i;d.rectangle((x,1510,x+45,1555),fill=COLOURS[code]);d.text((x+65,1511),LABEL[code],font=font(38),fill='#222222')
d.text((90,1610),'Unclear denotes insufficient reporting. Applicability is separate from risk of bias.',font=font(33),fill='#555555')
im.save(FIGS/'quadas2_domain_summary.png',dpi=(300,300))

traffickeys=['D1','D2','D3','D4','overall_risk','A1','A2','A3','overall_applicability']
for panel,start in enumerate(range(0,206,52),1):
 g=df.iloc[start:start+52];im=Image.new('RGB',(1800,2280),'white');d=ImageDraw.Draw(im)
 d.text((70,35),f'QUADAS-2 study ratings: {start+1}-{start+len(g)} of 206',font=font(43),fill='#222222')
 d.text((70,100),'Single AI reviewer; L = Low, H = High, U = Unclear',font=font(31),fill='#555555')
 d.text((70,180),'Study ID',font=font(32),fill='#222222')
 xs=[400+j*143 for j in range(9)]
 for x,k in zip(xs,['D1','D2','D3','D4','RoB','A1','A2','A3','App']):d.text((x+45,180),k,font=font(32),fill='#222222',anchor='mt')
 for j,(_,r) in enumerate(g.iterrows()):
  y=240+j*35
  if j%2==0:d.rectangle((60,y-2,1735,y+32),fill='#F4F5F6')
  d.text((80,y),r.id,font=font(29),fill='#222222')
  for x,k in zip(xs,traffickeys):
   c=r[k];d.rectangle((x,y,x+95,y+30),fill=COLOURS[c]);d.text((x+47,y+14),c,font=font(27),fill='white' if c!='U' else '#222222',anchor='mm')
 d.text((70,2110),'D1 selection | D2 index | D3 reference | D4 flow | RoB overall risk',font=font(29),fill='#444444')
 d.text((70,2160),'A1 sample | A2 index | A3 reference | App overall applicability',font=font(29),fill='#444444')
 d.text((70,2210),'Study titles, signalling answers, reasons and source locations: Supplementary Table S3.',font=font(25),fill='#555555')
 im.save(FIGS/f'quadas2_traffic_light_{panel}.png',dpi=(300,300))

# Accuracy illustration keeps each study as a point; no pooled diagnostic estimate.
im=Image.new('RGB',(2400,1330),'white');d=ImageDraw.Draw(im)
d.text((100,50),'Reported headline accuracy by overall risk',font=font(58),fill='#222222')
d.text((100,132),'Heterogeneous tasks and evaluation units; descriptive only',font=font(36),fill='#555555')
x0,x1=600,2250;top=270
for v in range(0,101,20):
 x=x0+(x1-x0)*v/100;d.line((x,top,x,1040),fill='#DDDDDD',width=2);d.text((x,1080),str(v),font=font(34),fill='#333333',anchor='mm')
rng=np.random.default_rng(20261028)
for j,c in enumerate(['L','U','H']):
 v=df.loc[df.overall_risk==c,'acc_pct'].dropna().to_numpy();y=400+j*260
 d.text((100,y-20),f'{LABEL[c]} (n = {len(v)})',font=font(42),fill='#222222')
 for value in v:
  x=x0+(x1-x0)*value/100;yy=y+float(rng.uniform(-60,60));d.ellipse((x-8,yy-8,x+8,yy+8),fill=COLOURS[c],outline='#444444',width=1)
 if len(v):
  q1,med,q3=np.quantile(v,[.25,.5,.75]);a=x0+(x1-x0)*q1/100;b=x0+(x1-x0)*q3/100;mx=x0+(x1-x0)*med/100
  d.line((a,y+90,b,y+90),fill='#222222',width=7);d.line((mx,y+73,mx,y+107),fill='#222222',width=7)
d.text((1400,1150),'As-extracted accuracy (%)',font=font(39),fill='#222222',anchor='mm')
d.text((100,1230),'Points = reports; line = IQR; tick = median. Remaining non-High reports are mainly Unclear.',font=font(32),fill='#555555')
im.save(FIGS/'quadas2_accuracy_sensitivity.png',dpi=(300,300))

result={'n':len(df),'overall_risk':df.overall_risk.value_counts().to_dict(),'overall_applicability':df.overall_applicability.value_counts().to_dict(),
 'domains':{k:df[k].value_counts().to_dict() for k in DOMAINS},'agar_n':int(df.agar.sum()),'accuracy_n':int(df.acc_pct.notna().sum()),
 'low_risk_ids':df.loc[df.overall_risk=='L','id'].tolist(),'review_date':'2026-10-28','reviewer':'single Codex AI reviewer',
 'not_done':['independent human assessment','second-reviewer consensus','inter-rater reliability','new outcome extraction','diagnostic meta-analysis','I-squared','publication-bias test']}
(OUT/'analysis_summary.json').write_text(json.dumps(result,indent=2))

study_fields=['id','title','year','task','unit','agar']+list(DOMAINS)+['overall_risk','overall_applicability','pages','scope_version_note','source_pdf','source_sha256']
study_data=[]
for _,r in df.iterrows():
 vals=[r[k] for k in study_fields]; vals=[LABEL.get(v,v) if k in list(DOMAINS)+['overall_risk','overall_applicability'] else v for k,v in zip(study_fields,vals)]
 study_data.append(vals)
payload={'studies':{'headers':study_fields,'rows':study_data},'domains':{'headers':list(long[0]),'rows':[list(r.values()) for r in long]},
 'signals':{'headers':list(sig[0]),'rows':[list(r.values()) for r in sig]},'summary':result,
 'distribution':summary.where(pd.notna(summary),None).to_dict('records'),
 'accuracy_sensitivity':acc.astype(object).where(pd.notna(acc),None).to_dict('records'),
 'protocol':(OUT/'assessment_protocol.txt').read_text().splitlines()}
(OUT/'workbook_input.json').write_text(json.dumps(payload,ensure_ascii=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
(OUT/'README.txt').write_text('QUADAS-2 source appraisal, 28 October 2026\n\n'+
 'All 206 reports received a new targeted manual methodological appraisal by one Codex AI reviewer. This is not independent human review, a second observer, or a blinded assessment. Prior extraction/tiering was available.\n\n'+
 'Primary decision record: manual_assessments.tsv. Full joined results: QUADAS2_study_assessments.csv. Each of seven domain/applicability decisions has a separate reason. Domain evidence and eleven signalling answers per report are exported separately. Overall labels are deterministic summaries, not a quality score.\n\n'+
 'Read assessment_protocol.txt for adaptation, judgement rules and limitations. Read consistency_audit.csv for same-reviewer refinements; this is not reviewer agreement. Scope/version concerns are retained explicitly. Source locations refer to local PDF page order or named sections.\n\n'+
 'Reproduce: run report_outputs/code/11_summarise_quadas2.py, then 11b_build_quadas2_workbook.mjs, then 12_update_quadas2_report.py, and finally 14_revise_section36_outcomes.py for the results presentation revised against EXAMPLE.docx. Domain ratings must be edited by a reviewer in the TSV; scripts do not infer them. The report builder starts its own pre-QUADAS backup to avoid duplicate insertion. Older builders 05/08/09 may overwrite newer outputs and must not be run over this snapshot without reapplying QUADAS work.\n\n'+
 'Figures: domain summary, four panels covering all 206 studies, and descriptive accuracy points. CSV point/summary data are under report_outputs/tables/quadas2_*. Numeric accuracy is reused from the earlier extraction, not independently re-extracted or harmonized in this appraisal. Excluding High risk retains Low plus Unclear, not a low-bias evidence base.\n\n'+
 'Source PDFs remain in papers/pdfs. SHA256 identifiers are preserved from the preceding source snapshot. No diagnostic meta-analysis, I-squared, inter-reviewer agreement, or publication-bias test is manufactured.\n')
print(json.dumps(result,indent=2))
print(acc.to_string(index=False,columns=['cohort','analysis','reports','accuracy_n','median','q1','q3']))
