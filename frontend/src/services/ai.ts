export type Connection={id:string;installed:boolean;authenticated:boolean;state:string;message:string};
export type AIModel={id:string;provider:string;label:string;account_usage?:boolean;estimated_cost_cny?:number};
export type Providers={cloud:{enabled:boolean;models:Record<string,number>;price_checked:string};connections:Record<string,Connection>;models:AIModel[]};
export type Generation={id:string;source_revision:string;provider:string;model:string;state:string;warning:string;error?:string;width?:number;height?:number;transparent?:boolean;format?:string};
