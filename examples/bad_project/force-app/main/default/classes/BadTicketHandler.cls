public class BadTicketHandler {
    public static void run(List<Service_Ticket__c> tickets) {
        for (Service_Ticket__c ticket : tickets) {
            Account owner = [SELECT Id FROM Account WHERE Id = '001000000000001AAA'];
            ticket.Owner_Note__c = 'for (checked) update ticket';
            update ticket;
        }
    }
}
