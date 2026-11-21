/**
 * Calculates and maintains SLA timestamps on Service_Ticket__c records.
 * All methods work on lists, so a bulk load of 200 records uses no queries and no DML.
 */
public with sharing class ServiceTicketSlaService {

    // Hours allowed to resolve a ticket, by priority.
    @TestVisible
    private static final Map<String, Integer> SLA_HOURS = new Map<String, Integer>{
        'Critical' => 4,
        'High' => 8,
        'Normal' => 24,
        'Low' => 72
    };

    private static final String DEFAULT_PRIORITY = 'Normal';

    /** Due time for a ticket opened at openedAt. A blank or unknown priority uses Normal. */
    public static Datetime calculateDue(String priority, Datetime openedAt) {
        if (openedAt == null) {
            return null;
        }
        Integer hours = SLA_HOURS.get(priority == null ? DEFAULT_PRIORITY : priority);
        if (hours == null) {
            hours = SLA_HOURS.get(DEFAULT_PRIORITY);
        }
        return openedAt.addHours(hours);
    }

    /** Before insert: stamp the opened time if it is blank and set the due time. */
    public static void applyOnInsert(List<Service_Ticket__c> tickets) {
        for (Service_Ticket__c ticket : tickets) {
            if (ticket.Opened_At__c == null) {
                ticket.Opened_At__c = System.now();
            }
            ticket.Sla_Due_At__c = calculateDue(ticket.Priority__c, ticket.Opened_At__c);
        }
    }

    /**
     * Before update: recalculate the due time when the priority changes, stamp the
     * resolved time when the ticket becomes Resolved, and record whether the SLA was met.
     */
    public static void applyOnUpdate(List<Service_Ticket__c> tickets, Map<Id, Service_Ticket__c> oldTickets) {
        for (Service_Ticket__c ticket : tickets) {
            Service_Ticket__c before = oldTickets.get(ticket.Id);
            if (ticket.Priority__c != before.Priority__c) {
                ticket.Sla_Due_At__c = calculateDue(ticket.Priority__c, ticket.Opened_At__c);
            }
            if (ticket.Status__c == 'Resolved' && ticket.Resolved_At__c == null) {
                ticket.Resolved_At__c = System.now();
            }
            if (ticket.Resolved_At__c != null && ticket.Sla_Due_At__c != null) {
                ticket.Sla_Met__c = ticket.Resolved_At__c <= ticket.Sla_Due_At__c;
            }
        }
    }
}
