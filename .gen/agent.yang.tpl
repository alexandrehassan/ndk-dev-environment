module support {
    yang-version 1.1;
    namespace "example.com/support";
    prefix "srl-labs-support";
    description
      "support YANG module";
    revision "2022-08-15" {
        description
          "initial release";
    }

    container support {
        description
          "support container";
        leaf run {
            type boolean;
            default false;
            description
              "run the support container";
        }
    }
}