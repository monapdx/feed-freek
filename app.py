import argparse, html, json, re, sqlite3, threading, time, urllib.request, urllib.parse, webbrowser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent
DB=ROOT/'reader.db'

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS feeds(id INTEGER PRIMARY KEY,url TEXT UNIQUE,title TEXT,site TEXT,error TEXT,last_checked INTEGER DEFAULT 0)')
 c.execute('CREATE TABLE IF NOT EXISTS articles(id INTEGER PRIMARY KEY,feed_id INTEGER,guid TEXT,title TEXT,url TEXT,summary TEXT,published INTEGER,read INTEGER DEFAULT 0,saved INTEGER DEFAULT 0, UNIQUE(feed_id,guid))')
 if 'discovered_at' not in {r['name'] for r in c.execute('PRAGMA table_info(articles)')}:
  c.execute('ALTER TABLE articles ADD COLUMN discovered_at INTEGER DEFAULT 0')
 c.commit(); return c

def stamp(s):
 if not s:return int(time.time())
 try:return int(parsedate_to_datetime(s).timestamp())
 except Exception:
  try:return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())
  except Exception:return int(time.time())
def clean(s):return re.sub(r'<[^>]*>',' ',html.unescape(s or '')).strip()[:1200]
def field(el,*names):
 for name in names:
  x=el.find(name)
  if x is not None and x.text:return x.text.strip()
 return ''
def parse(data,base):
 root=ET.fromstring(data)
 atom='{http://www.w3.org/2005/Atom}'
 if root.tag in ('rss','{http://purl.org/rss/1.0/}RDF','RDF'):
  ch=root.find('channel')
  if ch is None:ch=root
  title=field(ch,'title') or base
  site=field(ch,'link') or base
  items=[]
  for x in ch.findall('item')+root.findall('item'):
   url=field(x,'link'); guid=field(x,'guid') or url or field(x,'title')
   items.append((guid,field(x,'title') or '(untitled)',url,clean(field(x,'description','{http://purl.org/rss/1.0/modules/content/}encoded')),stamp(field(x,'pubDate','{http://purl.org/dc/elements/1.1/}date'))))
 else:
  title=field(root,atom+'title') or base
  link=root.find(atom+'link');site=link.get('href',base) if link is not None else base
  items=[]
  for x in root.findall(atom+'entry'):
   links=x.findall(atom+'link'); url=next((l.get('href','') for l in links if l.get('rel','alternate')=='alternate'),links[0].get('href','') if links else '')
   guid=field(x,atom+'id') or url or field(x,atom+'title')
   items.append((guid,field(x,atom+'title') or '(untitled)',url,clean(field(x,atom+'summary',atom+'content')),stamp(field(x,atom+'published',atom+'updated'))))
 return title,site,items

def refresh(feed):
 c=conn()
 try:
  req=urllib.request.Request(feed['url'],headers={'User-Agent':'Mozilla/5.0 RSS Reader/1.0','Accept':'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'})
  with urllib.request.urlopen(req,timeout=18) as response:data=response.read(4_000_000)
  title,site,items=parse(data,feed['url'])
  c.execute('UPDATE feeds SET title=?,site=?,error=NULL,last_checked=? WHERE id=?',(title,site,int(time.time()),feed['id']))
  discovered_at=time.time_ns()
  before=c.total_changes
  c.executemany('INSERT OR IGNORE INTO articles(feed_id,guid,title,url,summary,published,discovered_at) VALUES(?,?,?,?,?,?,?)',[(feed['id'],*i,discovered_at) for i in items if i[0]])
  c.commit();return {'id':feed['id'],'added':c.total_changes-before}
 except Exception as e:
  c.execute('UPDATE feeds SET error=?,last_checked=? WHERE id=?',(str(e)[:250],int(time.time()),feed['id']));c.commit()
  return {'id':feed['id'],'error':str(e)[:250]}
 finally:c.close()
class Handler(BaseHTTPRequestHandler):
 def send(self,obj,status=200,typ='application/json'):
  data=json.dumps(obj).encode() if typ=='application/json' else obj
  self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def body(self):
  try:return json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),1000000)))
  except Exception:return {}
 def do_GET(self):
  path=urllib.parse.urlsplit(self.path)
  if path.path in ('/', '/style.css', '/app.js'):
   name,typ={'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8')}[path.path]
   return self.send((ROOT/name).read_bytes(),typ=typ)
  c=conn()
  try:
   if path.path=='/api/stats':return self.send(dict(c.execute('SELECT count(*) total,coalesce(sum(read=0),0) unread,coalesce(sum(saved=1),0) saved FROM articles').fetchone()))
   if path.path=='/api/feeds':return self.send([dict(r) for r in c.execute('SELECT f.*, (SELECT count(*) FROM articles a WHERE a.feed_id=f.id AND a.read=0) unread FROM feeds f ORDER BY title')])
   if path.path=='/api/articles':
    q=urllib.parse.parse_qs(path.query); where=[];args=[]
    if q.get('feed',[''])[0].isdigit():where.append('a.feed_id=?');args.append(int(q['feed'][0]))
    mode=q.get('mode',['all'])[0]
    if mode=='unread':where.append('a.read=0')
    if mode=='saved':where.append('a.saved=1')
    search=q.get('q',[''])[0].strip()
    if search:where.append('(a.title LIKE ? OR a.summary LIKE ?)');args.extend(['%'+search+'%']*2)
    order={'received':'a.discovered_at DESC,a.published DESC,a.id DESC','published':'a.published DESC,a.id DESC','oldest':'a.published ASC,a.id ASC'}.get(q.get('sort',['received'])[0],'a.discovered_at DESC,a.published DESC,a.id DESC')
    sql='SELECT a.*,f.title feed_title FROM articles a JOIN feeds f ON f.id=a.feed_id'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY '+order+' LIMIT 500'
    return self.send([dict(r) for r in c.execute(sql,args)])
   if path.path=='/api/export':return self.send({'feeds':[r['url'] for r in c.execute('SELECT url FROM feeds ORDER BY title')]})
   self.send({'error':'Not found'},404)
  finally:c.close()
 def do_POST(self):
  p=self.path;b=self.body();c=conn()
  try:
   if p=='/api/feeds':
    url=b.get('url','').strip()
    if not url.startswith(('https://','http://')):return self.send({'error':'Enter a full http(s) feed URL.'},400)
    try:c.execute('INSERT INTO feeds(url,title) VALUES(?,?)',(url,url));c.commit()
    except sqlite3.IntegrityError:return self.send({'error':'Already subscribed.'},409)
    return self.send(refresh(dict(c.execute('SELECT * FROM feeds WHERE url=?',(url,)).fetchone())))
   if p=='/api/refresh':
    feeds=[dict(r) for r in c.execute('SELECT * FROM feeds'+(' WHERE id=?' if str(b.get('id','')).isdigit() else ''),((int(b['id']),) if str(b.get('id','')).isdigit() else ()))]
    return self.send([refresh(f) for f in feeds])
   if p=='/api/article':
    key=b.get('key');value=b.get('value');id=b.get('id')
    if key not in ('read','saved') or value not in (0,1,False,True) or not str(id).isdigit():return self.send({'error':'Invalid update'},400)
    c.execute(f'UPDATE articles SET {key}=? WHERE id=?',(int(value),int(id)));c.commit();return self.send({'ok':True})
   if p=='/api/mark-all':
    fid=b.get('feed');c.execute('UPDATE articles SET read=1 WHERE read=0'+(' AND feed_id=?' if str(fid).isdigit() else ''),((int(fid),) if str(fid).isdigit() else ()));c.commit();return self.send({'ok':True})
   if p=='/api/import':
    urls=b.get('urls',[])
    if not isinstance(urls,list):return self.send({'error':'Invalid import'},400)
    result=[]
    for u in urls[:500]:
     if isinstance(u,str) and u.startswith(('http://','https://')):
      c.execute('INSERT OR IGNORE INTO feeds(url,title) VALUES(?,?)',(u,u));c.commit()
      result.append(refresh(dict(c.execute('SELECT * FROM feeds WHERE url=?',(u,)).fetchone())))
    return self.send(result)
   self.send({'error':'Not found'},404)
  finally:c.close()
 def do_DELETE(self):
  if not self.path.startswith('/api/feeds/'):return self.send({'error':'Not found'},404)
  try:id=int(self.path.split('/')[-1])
  except ValueError:return self.send({'error':'Invalid ID'},400)
  c=conn();c.execute('DELETE FROM articles WHERE feed_id=?',(id,));c.execute('DELETE FROM feeds WHERE id=?',(id,));c.commit();c.close();self.send({'ok':True})
 def log_message(self,*args):pass
if __name__=='__main__':
 parser=argparse.ArgumentParser(description='FEED//FREAK local RSS reader')
 parser.add_argument('--port',type=int,default=8765)
 parser.add_argument('--no-browser',action='store_true')
 args=parser.parse_args()
 conn().close();server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
 address=f'http://127.0.0.1:{args.port}'
 print(f'FEED//FREAK: {address}')
 if not args.no_browser:webbrowser.open(address)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
