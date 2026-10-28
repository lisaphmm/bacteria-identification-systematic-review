"""Reproduce tier tables, exploratory statistics and Figure 5.

Tier judgements are read from the manually authored TSV, never inferred by code.
Requires Python 3 with pandas, numpy and Pillow. No API or model calls.
"""
import csv, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT/'report_outputs/tables'
FIGS = ROOT/'report_outputs/figures'
OUT = ROOT/'results/final/tier_review'
ORDER = ['S', 'I', 'II', 'III']
SEED, B = 20261028, 9999

def wilson(k, n):
    z = 1.959963984540054
    p, z2 = k/n, z*z
    centre = (p+z2/(2*n))/(1+z2/n)
    half = z*math.sqrt(p*(1-p)/n+z2/(4*n*n))/(1+z2/n)
    return max(0., centre-half), min(1., centre+half)

def write(df, path):
    df.to_csv(path, index=False, encoding='utf-8-sig', float_format='%.8f')

def counts(df, label):
    result=[]
    for tier in ORDER:
        k, n = int((df.tier==tier).sum()), len(df)
        lo, hi = wilson(k,n)
        result.append(dict(subgroup=label,tier=tier,n=k,denominator=n,percent=100*k/n,
                           ci_low_percent=lo*100,ci_high_percent=hi*100))
    return result

def accuracy_summary(df, cohort):
    result=[]
    for tier in ORDER:
        group=df[df.tier==tier]
        vals=group.acc_pct.dropna()
        result.append(dict(cohort=cohort,tier=tier,studies=len(group),n_accuracy=len(vals),
            missing_accuracy=len(group)-len(vals),median=vals.median(),
            q1=vals.quantile(.25),q3=vals.quantile(.75),minimum=vals.min(),maximum=vals.max()))
    return result

def permutation_kw(df, label):
    g=df.dropna(subset=['acc_pct'])
    levels=[t for t in ORDER if (g.tier==t).sum()]
    values=g.acc_pct.to_numpy(); n=len(g)
    if len(levels)<2:
        return dict(comparison=label,n=n,groups=len(levels),H=np.nan,p_permutation=np.nan)
    ranks=pd.Series(values).rank(method='average').to_numpy()
    masks=[np.flatnonzero(g.tier.to_numpy()==t) for t in levels]
    ns=np.array([len(m) for m in masks])
    _,ties=np.unique(values,return_counts=True)
    correction=1-np.sum(ties**3-ties)/(n**3-n)
    def h(rr):
        return (12/(n*(n+1))*sum(rr[m].sum()**2/len(m) for m in masks)-3*(n+1))/correction
    obs=h(ranks)
    rng=np.random.default_rng(SEED)
    exceed=sum(h(rng.permutation(ranks))>=obs-1e-12 for _ in range(B))
    return dict(comparison=label,n=n,groups=len(levels),group_n='; '.join(f'{t}:{n0}' for t,n0 in zip(levels,ns)),
                H=obs,p_permutation=(exceed+1)/(B+1),permutations=B,seed=SEED)

manual=pd.read_csv(OUT/'manual_decisions.tsv',sep='\t',keep_default_na=False)
inputs=pd.read_csv(TABLES/'tier_input.csv',keep_default_na=False)
coded=pd.read_csv(TABLES/'extraction_coded.csv',keep_default_na=False)
assert len(manual)==206 and manual.id.is_unique and set(manual.id)==set(inputs.id)
assert manual.tier.isin(ORDER).all() and manual.confidence.isin(['high','medium','low']).all()
df=inputs[['id','title','year']].merge(manual,on='id',validate='one_to_one').merge(
    coded.drop(columns=['year']),on='id',validate='one_to_one')
df.acc_pct=pd.to_numeric(df.acc_pct,errors='coerce')
assert df.acc_pct.dropna().between(0,100).all()
df['who decided']='Codex AI reviewer; individual source-based judgement, not human consensus'
df['human_verification']='Pending; no independent human tier adjudication recorded'
df['review_date']='2026-10-28'
df['setting']=df.tier.map({'S':'live prospective deployment','I':'routine clinical or field samples',
                         'II':'controlled lab images','III':'secondary image data'})
df['source_pdf']=df.id.map(lambda rid: f'papers/pdfs/{rid}.pdf')
df['source_sha256']=df.id.map(lambda rid: hashlib.sha256((ROOT/f'papers/pdfs/{rid}.pdf').read_bytes()).hexdigest())
df['source_page_count']=df.id.map(lambda rid: len(json.loads((OUT/f'source_text/{rid}.json').read_text())))
df['review_scope']='Targeted reading of acquisition, dataset and main evaluation passages in local full text; not all-page verification'
audit_cols=['id','title','year','tier','setting','confidence','pages','rationale','missing','who decided',
            'human_verification','review_date','source_pdf','source_sha256','source_page_count','review_scope']
write(df[audit_cols],ROOT/'results/final/evidence_tiers.csv')
df['feature_type']=np.where(df.morph_feat.astype(str).str.lower()=='true',
    'Explicit morphology/texture/topology/motility features recorded',
    'Learned image/spectral features; no explicit morphology/motility descriptor recorded')
matrix_cols=audit_cols+['agar','species','dataset','collect','dtype','feature_type','morph_text','model_family',
                      'model','tasks','ref','valid','acc','acc_pct','ext_valid','ds_AGAR','ds_DIBaS']
write(df[matrix_cols],TABLES/'supplementary_table_S2_tiers_and_synthesis.csv')
all_counts=[]
for label,g in [('All included',df),('Agar plates',df[df.agar]),('Other images',df[~df.agar])]:
    all_counts.extend(counts(g,label))
count_df=pd.DataFrame(all_counts)
write(count_df,TABLES/'evidence_tier_distribution.csv')
write(count_df[count_df.subgroup=='All included'],TABLES/'evidence_tier_figure_data.csv')
write(pd.crosstab(df.tier,df.model_family).reindex(ORDER,fill_value=0).reset_index(),TABLES/'evidence_tier_by_model_family.csv')
write(df[['id','tier','confidence','agar','acc_pct','acc','tasks','model_family','dataset','ds_AGAR','ds_DIBaS']],
      TABLES/'evidence_tier_accuracy_points.csv')
characteristics=[]
flag_fields=[c for c in coded.columns if c.startswith(('gen_','fam_','fac_')) and c!='fam_any_specific']
flag_fields += ['agar','ext_valid','cross_val','data_public','data_request','code_public',
                'ds_AGAR','ds_DIBaS','morph_feat','llm_vlm']
for label,g in [('All included',df),('Agar plates',df[df.agar])]:
    for field in flag_fields:
        present=g[field].astype(str).str.lower().eq('true')
        k,n=int(present.sum()),len(g);lo,hi=wilson(k,n)
        characteristics.append(dict(subgroup=label,characteristic_code=field,n=k,denominator=n,
            percent=k/n*100,ci_low_percent=lo*100,ci_high_percent=hi*100,
            interpretation='Reported/coded presence; a false flag is not proof of absence; categories can overlap'))
    for family,k in g.model_family.value_counts().items():
        n=len(g);lo,hi=wilson(int(k),n)
        characteristics.append(dict(subgroup=label,characteristic_code='primary_family: '+family,
            n=int(k),denominator=n,percent=k/n*100,ci_low_percent=lo*100,ci_high_percent=hi*100,
            interpretation='Primary model family as coded in the existing extraction'))
write(pd.DataFrame(characteristics),TABLES/'study_characteristic_proportions_95CI.csv')
acc_rows=[]
cohorts=[('All included',df),('Agar plates',df[df.agar]),('Other images',df[~df.agar]),
         ('Exclude low-confidence tiers',df[df.confidence!='low']),
         ('High-confidence tiers only',df[df.confidence=='high']),
         ('Exclude version/scope concerns',df[~df.id.isin(['R01154','R00395'])]),
         ('Exclude AGAR and DIBaS reuse flags',df[~(df.ds_AGAR|df.ds_DIBaS)])]
for label,g in cohorts: acc_rows.extend(accuracy_summary(g,label))
acc_df=pd.DataFrame(acc_rows)
write(acc_df,TABLES/'evidence_tier_accuracy_summary.csv')
sens=[]
for label,g in cohorts[3:]:sens.extend(counts(g,label))
write(pd.DataFrame(sens),TABLES/'evidence_tier_sensitivity_counts.csv')
tests=pd.DataFrame([permutation_kw(g,label) for label,g in cohorts[:3]])
tests['p_holm']=np.nan
inds=tests.p_permutation.dropna().sort_values().index
adj=0
for rank,idx in enumerate(inds):
    adj=max(adj,min(1.,tests.loc[idx,'p_permutation']*(len(inds)-rank)))
    tests.loc[idx,'p_holm']=adj
tests['interpretation']='Exploratory comparison of heterogeneous as-extracted headline accuracies; not model superiority or a pooled diagnostic effect'
write(tests,TABLES/'evidence_tier_exploratory_tests.csv')
write(df[df.confidence!='high'][audit_cols],OUT/'tier_verification_queue.csv')

# A worksheet for the independent human assessment, deliberately without fabricated ratings.
rob=df[['id','title','source_pdf']].copy()
for c in ['target_task','independent_unit','reviewer_1','reviewer_2','D1_sample_selection',
          'D2_index_test','D3_reference_standard','D4_flow_timing','A1_sample_applicability',
          'A2_index_applicability','A3_reference_applicability','overall_risk','overall_applicability',
          'supporting_evidence_and_pages','adjudicator','final_decision_date']:
    rob[c]=''
rob['assessment_status']='Not assessed independently by human reviewers'
write(rob,TABLES/'supplementary_table_S3_QUADAS2_assessment_worksheet.csv')

# Figure: study proportions with Wilson intervals, independent of model accuracy.
FIGS.mkdir(exist_ok=True)
canvas=Image.new('RGB',(2400,1420),'white'); draw=ImageDraw.Draw(canvas)
font_candidates=['/System/Library/Fonts/Supplemental/Arial.ttf','/Library/Fonts/Arial.ttf']
font_path=next((p for p in font_candidates if Path(p).exists()),None)
def font(n): return ImageFont.truetype(font_path,n) if font_path else ImageFont.load_default(size=n)
ink='#222222'; grey='#606060'; colours={'S':'#777777','I':'#009E73','II':'#0072B2','III':'#CC79A7'}
draw.text((110,65),'Realism of evaluation settings',font=font(62),fill=ink)
draw.text((110,155),'206 included studies | Individual source-based AI review',font=font(34),fill=grey)
left,right=550,1780
def x(v):return left+v/60*(right-left)
for tick in range(0,61,10):
    xx=x(tick);draw.line((xx,290,xx,1120),fill='#E1E1E1',width=2)
    draw.text((xx-18,1140),str(tick),font=font(30),fill=grey)
labels={'S':'Live prospective use','I':'Routine-origin samples','II':'Controlled laboratory','III':'Secondary image data'}
for i,row in enumerate(count_df[count_df.subgroup=='All included'].to_dict('records')):
    y=370+i*215;t=row['tier'];pc=row['percent'];lo=row['ci_low_percent'];hi=row['ci_high_percent']
    draw.text((110,y-52),f'Tier {t}',font=font(42),fill=ink)
    draw.text((110,y+9),labels[t],font=font(28),fill=grey)
    if pc>0:draw.rounded_rectangle((left,y-38,x(pc),y+38),radius=8,fill=colours[t])
    draw.line((x(lo),y,x(hi),y),fill=ink,width=5)
    for pos in [lo,hi]:draw.line((x(pos),y-16,x(pos),y+16),fill=ink,width=4)
    draw.text((1840,y-40),f'{row["n"]}/206  ({pc:.1f}%)',font=font(34),fill=ink)
    draw.text((1840,y+13),f'95% CI {lo:.1f}-{hi:.1f}%',font=font(28),fill=grey)
draw.text((1050,1205),'Share of studies (%)',font=font(34),fill=ink)
draw.text((110,1300),'Wilson 95% intervals describe study proportions. Tiers measure setting realism, not study quality.',font=font(28),fill=grey)
canvas.save(FIGS/'evidence_tier_distribution.png',dpi=(300,300))
summary={'n':len(df),'tier_counts':df.tier.value_counts().to_dict(),'confidence_counts':df.confidence.value_counts().to_dict(),
         'n_accuracy':int(df.acc_pct.notna().sum()),'overall_accuracy_median':df.acc_pct.median(),
         'overall_accuracy_q1':df.acc_pct.quantile(.25),'overall_accuracy_q3':df.acc_pct.quantile(.75),
         'reviewer':'Codex AI reviewer, not a human or dual-model consensus',
         'no_meta_analysis_reason':'No harmonised independent binary diagnostic 2x2 data; diverse tasks, organisms, acquisition, endpoints and sampling units',
         'tests':tests.fillna('').to_dict('records')}
(OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
