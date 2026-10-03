import {redirect} from "next/navigation";

type SearchValue=string|string[]|undefined;
export default async function LegacyTransactions({searchParams}:{searchParams:Promise<Record<string,SearchValue>>}){
  const values=await searchParams;
  const query=new URLSearchParams();
  for(const [key,value] of Object.entries(values)){for(const item of Array.isArray(value)?value:value?[value]:[])query.append(key,item)}
  redirect("/accounts"+(query.size?"?"+query.toString():""));
}
