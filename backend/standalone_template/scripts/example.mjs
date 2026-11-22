import fs from 'node:fs';
const key=fs.readFileSync(new URL('../.standalone-key',import.meta.url),'utf8').trim();
const env=fs.readFileSync(new URL('../.env',import.meta.url),'utf8');
const port=Number(env.match(/^API_PORT=(\d+)$/m)?.[1]||8020);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid configured API port');
const response=await fetch(`${process.env.STANDALONE_URL||`http://127.0.0.1:${port}`}/v1/query`,{
  method:'POST',redirect:'error',headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},
  body:JSON.stringify({question:'What is the refund period?'})
});
if(!response.ok)throw new Error(`Request failed: ${response.status}`);
console.log(await response.json());
