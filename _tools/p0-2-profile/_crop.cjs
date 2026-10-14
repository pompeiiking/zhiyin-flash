const fs=require('fs'),zlib=require('zlib');
function decode(buf){let pos=8,W=0,H=0,bd=0,ct=0,il=0;const idat=[];while(pos<buf.length){const len=buf.readUInt32BE(pos);const type=buf.toString('ascii',pos+4,pos+8);const d=buf.subarray(pos+8,pos+8+len);if(type==='IHDR'){W=d.readUInt32BE(0);H=d.readUInt32BE(4);bd=d[8];ct=d[9];il=d[12];}else if(type==='IDAT')idat.push(d);else if(type==='IEND')break;pos+=12+len;}
const bpp=ct===6?4:3;const raw=zlib.inflateSync(Buffer.concat(idat));const stride=W*bpp;const out=Buffer.alloc(H*stride);
const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
for(let y=0;y<H;y++){const f=raw[y*(stride+1)];const src=raw.subarray(y*(stride+1)+1,y*(stride+1)+1+stride);const cur=out.subarray(y*stride,(y+1)*stride);const prev=y>0?out.subarray((y-1)*stride,y*stride):null;
for(let x=0;x<stride;x++){const a=x>=bpp?cur[x-bpp]:0;const b=prev?prev[x]:0;const c=prev&&x>=bpp?prev[x-bpp]:0;let v=src[x];if(f===1)v+=a;else if(f===2)v+=b;else if(f===3)v+=(a+b)>>1;else if(f===4)v+=paeth(a,b,c);cur[x]=v&255;}}
return {W,H,bpp,data:out};}
function encode(W,H,bpp,data){const stride=W*bpp;const rows=Buffer.alloc(H*(stride+1));for(let y=0;y<H;y++){rows[y*(stride+1)]=0;data.copy(rows,y*(stride+1)+1,y*stride,(y+1)*stride);}
const ct=bpp===4?6:2;const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(W,0);ihdr.writeUInt32BE(H,4);ihdr[8]=8;ihdr[9]=ct;
const crcT=[];for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;crcT[n]=c>>>0;}
const crc=(b)=>{let c=0xffffffff;for(const x of b)c=crcT[(c^x)&255]^(c>>>8);return (c^0xffffffff)>>>0;};
const chunk=(type,data)=>{const len=Buffer.alloc(4);len.writeUInt32BE(data.length,0);const t=Buffer.from(type,'ascii');const c=Buffer.alloc(4);c.writeUInt32BE(crc(Buffer.concat([t,data])),0);return Buffer.concat([len,t,data,c]);};
return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',ihdr),chunk('IDAT',zlib.deflateSync(rows,{level:9})),chunk('IEND',Buffer.alloc(0))]);}
function crop(src,dst,x0,y0,w,h){const img=decode(fs.readFileSync(src));const bpp=img.bpp;const out=Buffer.alloc(w*h*bpp);for(let y=0;y<h;y++){const sy=y0+y;if(sy<0||sy>=img.H)continue;img.data.copy(out,y*w*bpp,sy*img.width*bpp+x0*bpp,sy*img.width*bpp+(x0+w)*bpp);}fs.writeFileSync(dst,encode(w,h,bpp,out));console.log('wrote',dst,w+'x'+h,'from',src);}
const tag=process.env.TAG;
crop('_shots/p0-2-profile/'+tag+'-profile-390.png','_shots/p0-2-profile/zoom-'+tag+'-390.png',0,1620,390,900);
crop('_shots/p0-2-profile/'+tag+'-profile-1280.png','_shots/p0-2-profile/zoom-'+tag+'-1280.png',300,900,760,560);
