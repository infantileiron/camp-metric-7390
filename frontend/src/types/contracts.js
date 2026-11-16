/** @typedef {{id:number,code:string,version:number,name:string,numerator:string,denominator:string,locked:boolean}} Metric */
/** @typedef {{id:number,class_code:string,day:string,mode:string,enrolled:number,attended:number,completed:number,refunds:number,voided:boolean}} Fact */
/** @typedef {{id:number,metric_id:number,state:string,result:object,approval:string,note:string}} Snapshot */
/** @typedef {{id:number,state:string,created:string,created_by:string,entries:number,max_seq:number}} Ledger */
/** @typedef {{seq:number,ledger_id:number,fact_id:number,action:string,class_code:string,day:string,before:object|null,after:object|null,actor:string,created:string}} Revision */
/** @typedef {{id:number,metric_id:number,ledger_id:number,cutoff_seq:number,date_from:string,date_to:string,result:object,created:string,created_by:string}} Retrial */
