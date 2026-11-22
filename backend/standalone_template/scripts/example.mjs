import fs from 'node:fs';
const key=fs.readFileSync(new URL('../.standalone-key',import.meta.url),'utf8').trim();
const response=await fetch(`${process.env.STANDALONE_URL||'http://localhost:8020'}/v1/query`,{
  method:'POST',headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},
  body:JSON.stringify({question:'What is the refund period?'})
});
if(!response.ok)throw new Error(`Request failed: ${response.status}`);
console.log(await response.json());
