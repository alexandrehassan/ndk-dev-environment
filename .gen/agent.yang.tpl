module {{ getenv "APPNAME" }} {
    yang-version 1.1;
    namespace "example.com/{{ getenv "APPNAME" }}";
    prefix "srl-labs-{{ getenv "APPNAME" }}";
    description
      "{{ getenv "APPNAME" }} YANG module";
    revision "2022-08-15" {
        description
          "initial release";
    }
    grouping thresholds {
        description
          "Thresholds to be monitored";
        leaf threshold {
            type uint32;
            default 1;
            description
              "threshold value";
        }
        leaf operator {
            type enumeration {
                enum "gt";
                enum "lt";
                enum "eq";
                enum "neq";
                enum "ge";
                enum "le";
            }
            default "gt";
            description
              "Operator to be used";
        }
    }
    container {{ getenv "APPNAME" }} {
        description
          "{{ getenv "APPNAME" }} container";
        list paths {
            key "path";
            description
              "Paths to be monitored";
            leaf path {
                type string;
                mandatory true;
            }
            leaf sampling-rate {
                type uint32;
                mandatory true;
                default 1;
                description
                  "Sampling rate in minutes";
            }
            uses thresholds;
            leaf-list intervals {
                type uint32;
                min-elements 1;
                default [1 5 15];
            }
        }
    }
}