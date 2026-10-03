import {fireEvent,render,screen} from "@testing-library/react";
import {useState} from "react";
import {describe,expect,it} from "vitest";

import {SearchPicker} from "./search-picker";


function Example(){
  const [value,setValue]=useState("");
  return <SearchPicker ariaLabel="Choose account" value={value} onChange={setValue} searchPlaceholder="Search accounts" options={[
    {value:"pnc",label:"PNC Spend account",description:"PNC · •••• 9051"},
    {value:"fidelity",label:"Fidelity Cash Management",description:"Fidelity · •••• 1234"},
  ]}/>;
}


describe("SearchPicker",()=>{
  it("filters options and selects the active result with the keyboard",()=>{
    render(<Example/>);
    fireEvent.click(screen.getByRole("button",{name:"Choose account"}));
    const search=screen.getByRole("combobox",{name:"Search accounts"});
    fireEvent.change(search,{target:{value:"9051"}});
    expect(screen.getByRole("option",{name:/PNC Spend account/})).toBeInTheDocument();
    expect(screen.queryByRole("option",{name:/Fidelity/})).not.toBeInTheDocument();
    fireEvent.keyDown(search,{key:"Enter"});
    expect(screen.getByRole("button",{name:"Choose account"})).toHaveTextContent("PNC Spend account");
    expect(screen.queryByRole("combobox",{name:"Search accounts"})).not.toBeInTheDocument();
  });
  it("renders group headings without changing option order",()=>{
    render(<SearchPicker ariaLabel="Choose category" value="" onChange={()=>{}} options={[
      {value:"phone",label:"Utilities → Phone",group:"Expenses"},
      {value:"rent",label:"Housing → Rent",group:"Expenses"},
      {value:"pnc",label:"PNC Spend · •••• 9051",group:"Transfers & account payments"},
    ]}/>);
    fireEvent.click(screen.getByRole("button",{name:"Choose category"}));
    expect(screen.getByText("Expenses")).toBeInTheDocument();
    expect(screen.getByText("Transfers & account payments")).toBeInTheDocument();
    expect(screen.getAllByRole("option").map(option=>option.textContent)).toEqual(["Utilities → Phone","Housing → Rent","PNC Spend · •••• 9051"]);
  });
});
