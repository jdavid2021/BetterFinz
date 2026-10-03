"use client";

import {Fragment,useEffect,useId,useMemo,useRef,useState} from "react";
import {Check,ChevronDown,Search} from "lucide-react";

export type SearchPickerOption={value:string;label:string;description?:string;keywords?:string;group?:string};

export function SearchPicker({value,options,onChange,placeholder="Choose",searchPlaceholder="Search…",ariaLabel,className="",disabled=false}:{value:string;options:SearchPickerOption[];onChange:(value:string)=>void;placeholder?:string;searchPlaceholder?:string;ariaLabel:string;className?:string;disabled?:boolean}){
  const [open,setOpen]=useState(false),[query,setQuery]=useState(""),[active,setActive]=useState(0);
  const root=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),listId=useId();
  const selected=options.find(option=>option.value===value);
  const filtered=useMemo(()=>{const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);return terms.length?options.filter(option=>{const text=`${option.label} ${option.description||""} ${option.keywords||""}`.toLowerCase();return terms.every(term=>text.includes(term))}):options},[options,query]);
  useEffect(()=>{if(!open)return;const close=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false)};document.addEventListener("pointerdown",close);window.requestAnimationFrame(()=>input.current?.focus());return()=>document.removeEventListener("pointerdown",close)},[open]);
  function choose(next:string){onChange(next);setOpen(false);setQuery("")}
  function move(delta:number){setActive(current=>Math.min(Math.max(current+delta,0),Math.max(filtered.length-1,0)))}
  return <div className={`search-picker ${open?"open ":""}${className}`} ref={root}>
    <button type="button" className="search-picker-trigger" disabled={disabled} aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} onClick={()=>{setOpen(current=>!current);setQuery("")}}><span>{selected?.label||placeholder}</span><ChevronDown/></button>
    {open&&<div className="search-picker-popover"><label className="search-picker-input"><Search/><input ref={input} value={query} onChange={event=>{setQuery(event.target.value);setActive(0)}} placeholder={searchPlaceholder} aria-label={searchPlaceholder} role="combobox" aria-expanded="true" aria-controls={listId} aria-activedescendant={filtered[active]?`${listId}-${active}`:undefined} onKeyDown={event=>{if(event.key==="ArrowDown"){event.preventDefault();move(1)}else if(event.key==="ArrowUp"){event.preventDefault();move(-1)}else if(event.key==="Enter"&&filtered[active]){event.preventDefault();choose(filtered[active].value)}else if(event.key==="Escape"){event.preventDefault();setOpen(false)}}}/></label>
      <div className="search-picker-results" id={listId} role="listbox" aria-label={ariaLabel}>{filtered.length?filtered.map((option,index)=><Fragment key={option.value}>{option.group&&option.group!==filtered[index-1]?.group&&<div className="search-picker-group" role="presentation">{option.group}</div>}<button type="button" id={`${listId}-${index}`} role="option" aria-selected={option.value===value} className={(index===active?" active":"")+(option.value===value?" selected":"")} onMouseEnter={()=>setActive(index)} onClick={()=>choose(option.value)}><span><strong>{option.label}</strong>{option.description&&<small>{option.description}</small>}</span>{option.value===value&&<Check/>}</button></Fragment>):<div className="search-picker-empty">No matches. Try a shorter name.</div>}</div>
    </div>}
  </div>
}
