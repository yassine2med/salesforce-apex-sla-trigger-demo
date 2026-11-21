trigger ServiceTicketSlaTrigger on Service_Ticket__c (before insert, before update) {
    if (Trigger.isInsert) {
        ServiceTicketSlaService.applyOnInsert(Trigger.new);
    } else {
        ServiceTicketSlaService.applyOnUpdate(Trigger.new, Trigger.oldMap);
    }
}
